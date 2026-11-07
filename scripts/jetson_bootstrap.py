import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid


sys.path.insert(0, str(Path(__file__).resolve().parent))
from jetson_deploy import DeployError, Layout, REQUIRED, SHA, System, allowed_payload, atomic_json, file_digest, readiness, trusted_path, validate_installed
from jetson_release import PAYLOAD_ROOTS, git_output


ACCOUNT = "cybervisual-deploy"
SETTINGS = Path("/etc/cybervisual/deploy.json")
UNIT = Path("/etc/systemd/system/cybervisual.service")
DEPLOY_HELPER = Path("/usr/local/lib/cybervisual-deploy/jetson_deploy.py")
DEPLOY_ENTRY = Path("/usr/local/sbin/cybervisual-deploy")
SUDOERS = Path("/etc/sudoers.d/cybervisual-deploy")
PATH_KEYS = {"CYBERVISUAL_CONFIG": "config", "CYBERVISUAL_MODEL_PATH": "model", "CYBERVISUAL_STATE_DIR": "device_state",
             "CYBERVISUAL_CAPTURE_DIR": "captures"}


def parse_environment(text):
    result = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            assignments = shlex.split(line, comments=False, posix=True)
        except ValueError:
            raise DeployError("unsupported_environment_syntax")
        if len(assignments) != 1 or "=" not in assignments[0]:
            raise DeployError("unsupported_environment_syntax")
        name, value = assignments[0].split("=", 1)
        if not name.startswith("CYBERVISUAL_") or not name.replace("_", "").isalnum() or name in result or name == "CYBERVISUAL_FRONTEND_DIST":
            raise DeployError("unsafe_environment")
        result[name] = value
    return result


def runtime_settings(environment, root, port):
    environment = Path(environment)
    validate_persistent_path(environment, root)
    values = parse_environment(environment.read_text())
    settings = {"environment": str(environment.resolve()), "http_port": port}
    for name, key in PATH_KEYS.items():
        value = values.get(name, "")
        path = Path(value)
        validate_persistent_path(path, root)
        if (key in ("config", "model") and not path.is_file()) or (key in ("device_state", "captures") and not path.is_dir()):
            raise DeployError("persistent_path_required")
        settings[key] = str(path.resolve())
    configuration = json.loads(Path(settings["config"]).read_text())
    if not isinstance(configuration, dict):
        raise DeployError("invalid_runtime_config")
    source = values.get("CYBERVISUAL_SOURCE", configuration.get("source", "camera"))
    detector = values.get("CYBERVISUAL_DETECTOR", configuration.get("detector_backend", "auto"))
    if source != "camera" or detector not in ("auto", "opencv", "tensorrt"):
        raise DeployError("real_camera_and_detector_required")
    if values.get("CYBERVISUAL_PORT") != str(port) or not 1 <= port <= 65535:
        raise DeployError("http_port_mismatch")
    settings["models"] = str(Path(settings["model"]).parent)
    return settings


def validate_persistent_path(path, root):
    path = Path(path)
    value = str(path)
    if not path.is_absolute() or not path.exists() or any(character in value for character in ("%", "\n", "\r", " ", "\t")):
        raise DeployError("persistent_path_required")
    forbidden = [Path(root) / "releases", Path(root) / "current"]
    if any(path == parent or parent in path.parents or path.resolve() == parent.resolve() or parent.resolve() in path.resolve().parents for parent in forbidden):
        raise DeployError("release_scoped_persistence")


def service_values(text):
    allowed = {"Type", "WorkingDirectory", "Environment", "EnvironmentFile", "ExecStart", "Restart", "RestartSec",
               "TimeoutStopSec", "KillSignal", "StateDirectory", "StateDirectoryMode", "User", "Group"}
    section = None
    values = {}
    environment = {}
    environment_files = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section != "Service":
            continue
        if "=" not in line or line.endswith("\\"):
            raise DeployError("legacy_unit_requires_manual_review")
        name, value = line.split("=", 1)
        if name not in allowed:
            raise DeployError("legacy_unit_requires_manual_review")
        if name == "Environment":
            for assignment in shlex.split(value):
                if "=" not in assignment:
                    raise DeployError("legacy_unit_requires_manual_review")
                key, content = assignment.split("=", 1)
                environment[key] = content
        elif name == "EnvironmentFile":
            paths = shlex.split(value)
            if len(paths) != 1 or any(character in paths[0] for character in ("%", "*", "?", "[")):
                raise DeployError("legacy_unit_requires_manual_review")
            optional = paths[0].startswith("-")
            path = Path(paths[0].lstrip("-"))
            if not path.is_absolute() or (not optional and not path.is_file()):
                raise DeployError("legacy_unit_requires_manual_review")
            if path.is_file():
                environment_files.append(path)
        elif name in values:
            raise DeployError("legacy_unit_requires_manual_review")
        else:
            values[name] = value
    for path in environment_files:
        environment.update(parse_environment(path.read_text()))
    return values, environment, environment_files


def verify_migration(unit, old_root, candidate, settings):
    values, original, files = service_values(unit)
    old_root = Path(old_root).resolve()
    if values.get("WorkingDirectory") != str(old_root) or values.get("ExecStart") != str(old_root / "scripts/run_backend.sh") or values.get("User", "root") != "root" or values.get("Group", "root") != "root":
        raise DeployError("legacy_unit_requires_manual_review")
    original_config = Path(original.get("CYBERVISUAL_CONFIG", str(old_root / "backend/config.example.json")))
    if not original_config.is_absolute():
        original_config = old_root / original_config
    if not original_config.is_file() or original_config.resolve() != Path(settings["config"]):
        raise DeployError("legacy_paths_not_preserved")
    configuration = json.loads(original_config.read_text())
    paths = {
        "CYBERVISUAL_CONFIG": str(original_config),
        "CYBERVISUAL_MODEL_PATH": original.get("CYBERVISUAL_MODEL_PATH", configuration.get("model_path", "")),
        "CYBERVISUAL_STATE_DIR": original.get("CYBERVISUAL_STATE_DIR", str(old_root / ".cybervisual")),
        "CYBERVISUAL_CAPTURE_DIR": original.get("CYBERVISUAL_CAPTURE_DIR", str(old_root / "captures")),
    }
    for name, value in paths.items():
        if not value:
            raise DeployError("legacy_paths_not_preserved")
        path = Path(value) if Path(value).is_absolute() else old_root / value
        if not path.exists() or path.resolve() != Path(settings[PATH_KEYS[name]]):
            raise DeployError("legacy_paths_not_preserved")
    for name, value in original.items():
        if name in PATH_KEYS or name in ("PYTHONPATH", "CYBERVISUAL_FRONTEND_DIST"):
            continue
        if not name.startswith("CYBERVISUAL_") or candidate.get(name) != value:
            raise DeployError("legacy_environment_not_preserved")
    defaults = {"CYBERVISUAL_PORT": "8000", "CYBERVISUAL_HOST": "0.0.0.0",
                "CYBERVISUAL_SOURCE": configuration.get("source", "camera"),
                "CYBERVISUAL_DETECTOR": configuration.get("detector_backend", "auto")}
    for name in set(candidate) - set(original) - set(PATH_KEYS):
        if name not in defaults or candidate[name] != str(defaults[name]):
            raise DeployError("legacy_environment_not_preserved")
    models = old_root / "models"
    if models.exists():
        validate_persistent_path(models, "/opt/cybervisual")
        if not models.is_dir():
            raise DeployError("legacy_paths_not_preserved")
    return {"working_directory": str(old_root), "environment_files": files, "models": str(models.resolve())}


def command(arguments, timeout=30):
    try:
        return subprocess.check_output(arguments, stderr=subprocess.DEVNULL, timeout=timeout).decode("utf-8").strip()
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise DeployError("preparation_command_failed")


def prerequisites(python):
    failures = []
    if platform.machine().lower() not in ("aarch64", "arm64"):
        failures.append("ARM64 Jetson required; do not prepare a runner or workstation")
    if not Path("/etc/nv_tegra_release").is_file():
        failures.append("JetPack/L4T missing; install a supported NVIDIA JetPack image manually")
    probe = "import sys,venv,ensurepip,cv2,re; assert sys.version_info >= (3,6); assert re.search(r'GStreamer:\\s+YES',cv2.getBuildInformation())"
    try:
        command([python, "-c", probe])
    except DeployError:
        failures.append("Target Python >=3.6, venv/ensurepip and JetPack OpenCV with GStreamer are required; install python3-venv/python3-opencv through apt")
    for executable in ("systemctl", "systemd-run", "tailscale", "gst-inspect-1.0", "sudo", "visudo", "git", "useradd"):
        if not shutil.which(executable):
            failures.append("Missing command: " + executable)
    if not Path("/run/systemd/system").is_dir():
        failures.append("A running systemd system instance is required")
    try:
        command(["gst-inspect-1.0", "--version"])
        command(["systemctl", "is-active", "tailscaled.service"])
        preferences = json.loads(command(["tailscale", "debug", "prefs"]))
        if preferences.get("RunSSH") is not True:
            raise DeployError("tailscale_ssh_disabled")
    except (DeployError, ValueError):
        failures.append("GStreamer/tailscaled must be available and Tailscale SSH enabled by an administrator: sudo tailscale set --ssh")
    return failures


def install_file(source, destination, mode):
    destination = Path(destination)
    if destination.is_symlink():
        raise DeployError("unsafe_installation")
    destination.parent.mkdir(parents=True, exist_ok=True)
    trusted_path(destination.parent, directory=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".cybervisual-", dir=str(destination.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(source)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, str(destination))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_legacy_payload(root, commit, layout):
    if not SHA.fullmatch(commit) or git_output(root, "rev-parse", "HEAD").decode().strip() != commit:
        raise DeployError("legacy_commit_not_confirmed")
    if git_output(root, "status", "--porcelain", "--untracked-files=all", "--", *PAYLOAD_ROOTS):
        raise DeployError("legacy_payload_not_clean")
    python = root / ".venv/bin/python"
    if not python.is_file() or layout.releases in python.resolve().parents:
        raise DeployError("legacy_venv_not_confirmed")
    trusted_path((root / ".venv").resolve(), directory=True)
    names = git_output(root, "ls-files", "-z", "--", *PAYLOAD_ROOTS).decode().split("\0")
    names = [name for name in names if name and allowed_payload(name)]
    if not REQUIRED.issubset(names) or any((root / name).is_symlink() for name in names):
        raise DeployError("legacy_payload_not_clean")
    return names


def legacy_baseline(root, commit, layout, settings):
    names = verify_legacy_payload(root, commit, layout)
    readiness(System(), root, settings["http_port"])
    target = layout.releases / commit
    if target.exists():
        raise DeployError("legacy_baseline_already_exists")
    staging = Path(tempfile.mkdtemp(prefix=".legacy-", dir=str(layout.releases)))
    files = {}
    try:
        for name in names:
            source = root / name
            destination = staging / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(source), str(destination))
            destination.chmod(0o755 if name == "scripts/run_backend.sh" else 0o644)
            files[name] = file_digest(destination)
        os.symlink(str(root / ".venv"), str(staging / ".venv"))
        os.symlink(settings["models"], str(staging / "models"))
        atomic_json(staging / "release-manifest.json", {"format": 1, "commit": commit, "files": files})
        validate_installed(staging, commit)
        atomic_json(staging / ".release.json", {"commit": commit, "bundle_sha256": "legacy", "successful_at": time.time()})
        os.replace(str(staging), str(target))
    finally:
        if staging.exists():
            shutil.rmtree(str(staging))
    layout.switch(commit)
    atomic_json(layout.state / "state.json", {"current": commit, "previous": None})


@contextmanager
def preparation_transaction(layout, legacy_commit=None):
    snapshots = []
    for path in (DEPLOY_HELPER, DEPLOY_ENTRY, SUDOERS, UNIT, SETTINGS, layout.state / "state.json"):
        if path.is_symlink():
            raise DeployError("unsafe_installation")
        if path.exists():
            trusted_path(path)
            snapshots.append((path, path.read_bytes(), path.stat().st_mode & 0o777))
        else:
            snapshots.append((path, None, None))
    previous = layout.current_sha()
    baseline = layout.releases / legacy_commit if legacy_commit else None
    baseline_existed = baseline is not None and baseline.exists()
    try:
        yield
    except Exception:
        failed = False
        for path, content, mode in reversed(snapshots):
            try:
                if content is not None:
                    install_file(content, path, mode)
                elif path.exists():
                    path.unlink()
            except Exception:
                failed = True
        try:
            if previous:
                layout.switch(previous)
            elif layout.current.is_symlink():
                layout.current.unlink()
            if baseline is not None and not baseline_existed and baseline.exists():
                shutil.rmtree(str(baseline))
        except Exception:
            failed = True
        try:
            command(["systemctl", "daemon-reload"])
        except Exception:
            failed = True
        if failed:
            raise DeployError("preparation_rollback_failed")
        raise


def prepare(arguments):
    repository = Path(__file__).resolve().parents[1]
    layout = Layout()
    if SETTINGS.is_file():
        trusted_path(SETTINGS)
    existing = json.loads(SETTINGS.read_text()) if SETTINGS.is_file() else None
    environment = Path(arguments.runtime_env or (existing or {}).get("environment", "/etc/cybervisual/camera.env"))
    port = arguments.http_port if arguments.http_port is not None else (existing or {}).get("http_port", 8000)
    python = arguments.python or (existing or {}).get("python", "/usr/bin/python3")
    failures = prerequisites(python)
    for failure in failures:
        print("NOT READY: " + failure, file=sys.stderr)
    if failures:
        raise DeployError("device_prerequisites_missing")
    settings = runtime_settings(environment, layout.root, port)
    settings["python"] = str(Path(python).resolve())
    trusted_path(environment)
    trusted_path(Path(python).resolve())
    fragment = command(["systemctl", "show", "cybervisual.service", "--property=FragmentPath", "--value"])
    unit = command(["systemctl", "cat", "cybervisual.service"]) if fragment else ""
    migration = None
    if existing:
        settings["models"] = existing["models"]
        if any(existing.get(name) != value for name, value in settings.items()):
            raise DeployError("persistent_settings_changed_requires_manual_review")
        trusted_path(SETTINGS)
        if file_digest(UNIT) != existing.get("unit_sha256"):
            raise DeployError("managed_unit_changed_requires_manual_review")
    elif fragment:
        if not arguments.confirm_migration or not arguments.migrate_from or not arguments.legacy_sha:
            raise DeployError("explicit_legacy_migration_required")
        if command(["systemctl", "show", "cybervisual.service", "--property=DropInPaths", "--value"]):
            raise DeployError("legacy_dropins_require_manual_review")
        migration = verify_migration(unit, Path(arguments.migrate_from), parse_environment(environment.read_text()), settings)
        settings["models"] = migration["models"]
        verify_legacy_payload(Path(arguments.migrate_from).resolve(), arguments.legacy_sha, layout)
    elif any((arguments.confirm_migration, arguments.migrate_from, arguments.legacy_sha)):
        raise DeployError("legacy_service_not_found")
    if not existing and (layout.current.exists() or layout.current.is_symlink()):
        raise DeployError("unmanaged_current_link_requires_review")
    print("Device prerequisites and explicit persistent paths verified.")
    if not arguments.apply:
        print("CHECK ONLY: no account, file, service or tailnet changes. Re-run with --apply as an administrator when ready.")
        return
    if os.geteuid() != 0:
        raise DeployError("root_required")
    os.umask(0o022)
    if layout.root.exists():
        trusted_path(layout.root, directory=True)
    layout.prepare()
    for directory in (layout.root, layout.releases, layout.state, layout.jobs):
        trusted_path(directory, directory=True)
    with (layout.state / "submit.lock").open("a") as submission, layout.lock.open("a") as handle:
        try:
            fcntl.flock(submission, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DeployError("deployment_busy")
        for directory in layout.jobs.iterdir():
            status = directory / "status.json"
            if status.is_file() and json.loads(status.read_text()).get("phase") not in ("failed", "succeeded"):
                raise DeployError("pending_deployment_requires_review")
        backup = layout.state / "backups" / (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8])
        backup.mkdir(parents=True, mode=0o700)
        for name, content in (("service.unit", unit.encode()), ("runtime.env", environment.read_bytes()),
                              ("config.json", Path(settings["config"]).read_bytes())):
            install_file(content, backup / name, 0o600)
        try:
            account = pwd.getpwnam(ACCOUNT)
            groups = os.getgrouplist(ACCOUNT, account.pw_gid)
            if account.pw_uid == 0 or account.pw_dir != "/var/lib/cybervisual-deploy-user" or groups != [account.pw_gid] or account.pw_shell != "/bin/bash":
                raise DeployError("existing_deploy_account_requires_review")
        except KeyError:
            command(["useradd", "--system", "--user-group", "--create-home", "--home-dir", "/var/lib/cybervisual-deploy-user", "--shell", "/bin/bash", ACCOUNT])
        command(["passwd", "--lock", ACCOUNT])
        sudoers = ('Defaults:cybervisual-deploy env_reset\n'
                   'Defaults:cybervisual-deploy secure_path="/usr/sbin:/usr/bin:/sbin:/bin"\n'
                   'cybervisual-deploy ALL=(root) NOPASSWD: NOSETENV: /usr/local/sbin/cybervisual-deploy\n')
        descriptor, temporary = tempfile.mkstemp()
        try:
            with os.fdopen(descriptor, "w") as handle:
                handle.write(sudoers)
            command(["visudo", "--check", "--file", temporary])
        finally:
            os.unlink(temporary)
        with preparation_transaction(layout, arguments.legacy_sha if migration else None):
            if migration:
                for number, path in enumerate(migration["environment_files"]):
                    install_file(path.read_bytes(), backup / ("legacy-environment-%d.env" % number), 0o600)
                legacy_baseline(Path(arguments.migrate_from).resolve(), arguments.legacy_sha, layout, settings)
            install_file((repository / "scripts/jetson_deploy.py").read_bytes(), DEPLOY_HELPER, 0o644)
            install_file((repository / "scripts/deploy_jetson.sh").read_bytes(), DEPLOY_ENTRY, 0o755)
            install_file(sudoers.encode(), SUDOERS, 0o440)
            template = (repository / "deploy/systemd/cybervisual-release.service").read_text()
            managed = template.replace("@RUNTIME_ENV@", str(environment.resolve())).encode()
            install_file(managed, UNIT, 0o644)
            settings["unit_sha256"] = hashlib.sha256(managed).hexdigest()
            settings["deployer_sha256"] = file_digest(repository / "scripts/jetson_deploy.py")
            SETTINGS.parent.mkdir(parents=True, exist_ok=True)
            trusted_path(SETTINGS.parent, directory=True)
            atomic_json(SETTINGS, settings)
            command(["systemctl", "daemon-reload"])
            command(["systemctl", "enable", "cybervisual.service"])
    print("Prepared fixed deploy entry and service; no service started/restarted and no tailnet policy changed.")
    print("Root-only backup: " + str(backup))


def main():
    parser = argparse.ArgumentParser(description="Jetson deployment preparation; read-only unless --apply is explicitly supplied")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--runtime-env")
    parser.add_argument("--http-port", type=int)
    parser.add_argument("--python")
    parser.add_argument("--migrate-from")
    parser.add_argument("--legacy-sha")
    parser.add_argument("--confirm-migration", action="store_true")
    arguments = parser.parse_args()
    try:
        prepare(arguments)
        return 0
    except Exception as error:
        print("Preparation stopped: " + (str(error) if isinstance(error, DeployError) else "unreadable_or_unsupported_configuration"), file=sys.stderr)
        print("See docs/jetson-deploy.md; do not overwrite unknown configuration, models, venvs or device state.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
