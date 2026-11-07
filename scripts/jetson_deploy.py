import argparse
import contextlib
import fcntl
import hashlib
from html.parser import HTMLParser
import http.client
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import urlsplit
import uuid


SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
JOB = re.compile(r"^[0-9a-f]{32}$")
MAX_UPLOAD = 128 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
MAX_FILES = 10000
HELPER = "/usr/local/lib/cybervisual-deploy/jetson_deploy.py"
REQUIRED = {"backend/cybervisual/__init__.py", "backend/cybervisual/app.py", "backend/requirements.txt",
            "scripts/run_backend.sh", "frontend/dist/index.html"}
CHECK_FIELDS = {"service_active", "homepage", "assets", "api", "camera_connected", "model_loaded", "frame_advances"}
PUBLIC_FIELDS = {"job", "operation", "commit", "previous", "current", "phase", "error", "rollback",
                 "checks", "recovery_checks", "temperature_warning", "created_at", "finished_at", "http_port", "maintenance_warning"}
TERMINAL = {"succeeded", "failed"}


class DeployError(RuntimeError):
    def __init__(self, code, checks=None, temperature_warning=False):
        super().__init__(code)
        self.checks = checks or {}
        self.temperature_warning = temperature_warning


def read_json(path):
    with Path(path).open() as handle:
        return json.load(handle)


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name("." + path.name + "-" + uuid.uuid4().hex)
    descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def allowed_payload(name):
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        return False
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or str(path) != name:
        return False
    if re.fullmatch(r"backend/cybervisual/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\.py", name):
        return True
    if name in ("backend/requirements.txt", "scripts/run_backend.sh", "frontend/dist/index.html", "frontend/dist/fonts.css"):
        return True
    if re.fullmatch(r"frontend/dist/assets/[A-Za-z0-9_/-]+\.(?:js|css|svg|png|ico)", name):
        return True
    return bool(re.fullmatch(r"frontend/dist/fonts/[A-Za-z0-9_-]+\.(?:ttf|woff2?|txt)", name))


def validate_archive(path, commit, digest):
    if not SHA.fullmatch(commit) or not DIGEST.fullmatch(digest):
        raise DeployError("invalid_identity")
    if Path(path).stat().st_size > MAX_UPLOAD:
        raise DeployError("archive_too_large")
    if file_digest(path) != digest:
        raise DeployError("checksum_mismatch")
    try:
        with tarfile.open(str(path), "r:gz") as archive:
            names = set()
            hashes = {}
            total = 0
            manifest = None
            for member in archive:
                if len(names) >= MAX_FILES or member.name in names or not member.isfile() or member.mode & 0o7000:
                    raise DeployError("unsafe_archive")
                if member.name != "release-manifest.json" and not allowed_payload(member.name):
                    raise DeployError("unsafe_archive")
                names.add(member.name)
                total += member.size
                if member.size < 0 or total > MAX_EXPANDED or (member.name == "release-manifest.json" and member.size > 2 * 1024 * 1024):
                    raise DeployError("archive_too_large")
                content = archive.extractfile(member)
                if member.name == "release-manifest.json":
                    manifest = json.loads(content.read().decode("utf-8"))
                else:
                    checksum = hashlib.sha256()
                    for chunk in iter(lambda: content.read(1024 * 1024), b""):
                        checksum.update(chunk)
                    hashes[member.name] = checksum.hexdigest()
            if not isinstance(manifest, dict) or manifest.get("format") != 1:
                raise DeployError("invalid_manifest")
            if manifest.get("commit") != commit:
                raise DeployError("commit_mismatch")
            if not REQUIRED.issubset(hashes) or manifest.get("files") != hashes:
                raise DeployError("file_checksum_mismatch")
            if not any(name.endswith(".js") for name in hashes) or not any(name.endswith(".css") for name in hashes):
                raise DeployError("missing_frontend_assets")
            return manifest
    except (tarfile.TarError, ValueError, UnicodeError, EOFError, OSError):
        raise DeployError("invalid_archive")


def validate_installed(directory, commit):
    try:
        manifest = read_json(directory / "release-manifest.json")
        if manifest.get("commit") != commit or not REQUIRED.issubset(manifest["files"]):
            raise DeployError("release_not_valid")
        for name, digest in manifest["files"].items():
            path = directory / name
            if not allowed_payload(name) or path.is_symlink() or not path.is_file() or file_digest(path) != digest:
                raise DeployError("release_not_valid")
        if not (directory / ".venv/bin/python").is_file():
            raise DeployError("release_not_valid")
    except (OSError, ValueError, KeyError, TypeError):
        raise DeployError("release_not_valid")


class Layout:
    def __init__(self, root=Path("/opt/cybervisual"), state=Path("/var/lib/cybervisual-deploy")):
        self.root = Path(root)
        self.state = Path(state)
        self.releases = self.root / "releases"
        self.current = self.root / "current"
        self.jobs = self.state / "jobs"
        self.lock = self.state / "deploy.lock"

    def prepare(self):
        self.releases.mkdir(parents=True, exist_ok=True)
        self.jobs.mkdir(parents=True, exist_ok=True, mode=0o700)

    def current_sha(self):
        if not self.current.is_symlink():
            if self.current.exists():
                raise DeployError("unsafe_current_link")
            return None
        resolved = self.current.resolve()
        if resolved.parent != self.releases.resolve() or not SHA.fullmatch(resolved.name) or not resolved.is_dir():
            raise DeployError("unsafe_current_link")
        return resolved.name

    def switch(self, commit):
        temporary = self.root / (".current-" + uuid.uuid4().hex)
        os.symlink("releases/" + commit, str(temporary))
        try:
            os.replace(str(temporary), str(self.current))
        finally:
            if temporary.is_symlink():
                temporary.unlink()


class PageAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        value = attributes.get("src") if tag == "script" else attributes.get("href") if tag == "link" and attributes.get("rel") == "stylesheet" else None
        if value:
            parsed = urlsplit(value)
            if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or not value.startswith("/") or ".." in PurePosixPath(value).parts:
                raise DeployError("invalid_asset_reference")
            self.paths.add(value)


class DeadlineReader(io.RawIOBase):
    def __init__(self, stream, connection, deadline, clock):
        super().__init__()
        self.stream = stream
        self.connection = connection
        self.deadline = deadline
        self.clock = clock

    def readable(self):
        return True

    def readinto(self, buffer):
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise DeployError("http_unavailable")
        self.connection.settimeout(min(3, remaining))
        return self.stream.readinto(buffer)

    def close(self):
        try:
            self.stream.close()
        finally:
            super().close()


class DeadlineResponse(http.client.HTTPResponse):
    def __init__(self, connection, deadline, clock, **arguments):
        super().__init__(connection, **arguments)
        self.fp = io.BufferedReader(DeadlineReader(self.fp.detach(), connection, deadline, clock))


class System:
    def __init__(self):
        self.deadline = None

    def launch(self, job):
        try:
            subprocess.run([
                "/usr/bin/systemd-run", "--quiet", "--collect", "--no-block", "--unit=cybervisual-deploy-" + job,
                "--property=Type=oneshot", "--property=TimeoutStartSec=1800", "--property=UMask=0022",
                "/usr/bin/python3", "-I", HELPER, "_apply", job,
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except (OSError, subprocess.SubprocessError):
            raise DeployError("worker_start_failed")

    def install(self, directory, python):
        environment = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "HOME": "/root", "LC_ALL": "C.UTF-8"}
        try:
            subprocess.run([python, "-m", "venv", "--system-site-packages", str(directory / ".venv")],
                           check=True, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            executable = str(directory / ".venv/bin/python")
            subprocess.run([executable, "-m", "pip", "--isolated", "install", "--disable-pip-version-check", "--no-input",
                            "--no-cache-dir", "--timeout", "30", "--retries", "2", "--index-url", "https://pypi.org/simple",
                            "-r", str(directory / "backend/requirements.txt")], check=True, env=environment,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
            subprocess.run([executable, "-c", "import cv2, numpy"], check=True, env=environment,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except (OSError, subprocess.SubprocessError):
            raise DeployError("dependency_install_failed")

    def restart(self):
        self._control("restart")

    def stop(self):
        self._control("stop")

    def _control(self, operation):
        try:
            subprocess.run(["/bin/systemctl", operation, "cybervisual.service"], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except (OSError, subprocess.SubprocessError):
            raise DeployError("service_control_failed")

    def active(self):
        try:
            result = subprocess.run(["/bin/systemctl", "is-active", "--quiet", "cybervisual.service"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def monotonic(self):
        return time.monotonic()

    def sleep(self, seconds):
        time.sleep(seconds)

    def get(self, port, path):
        deadline = self.deadline if self.deadline is not None else self.monotonic() + 3
        remaining = deadline - self.monotonic()
        if remaining <= 0:
            raise DeployError("http_unavailable")
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=min(3, remaining))
        connection.response_class = lambda sock, **arguments: DeadlineResponse(sock, deadline, self.monotonic, **arguments)
        response = None
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            if response.status != 200:
                raise DeployError("http_unavailable")
            chunks = []
            total = 0
            while True:
                if self.deadline is not None and self.monotonic() >= self.deadline:
                    raise DeployError("http_unavailable")
                chunk = response.read1(65536)
                if not chunk:
                    return b"".join(chunks)
                total += len(chunk)
                if total > 16 * 1024 * 1024:
                    raise DeployError("http_unavailable")
                chunks.append(chunk)
        except (OSError, http.client.HTTPException):
            raise DeployError("http_unavailable")
        finally:
            if response is not None:
                response.close()
            connection.close()


def readiness(system, directory, port, timeout=180):
    deadline = system.monotonic() + timeout
    system.deadline = deadline
    previous_frame = None
    advances = 0
    warning = False
    checks = {}
    try:
        while system.monotonic() < deadline:
            checks = {name: False for name in CHECK_FIELDS}
            checks["frame_advances"] = advances
            try:
                checks["service_active"] = system.active()
                if not checks["service_active"]:
                    raise DeployError("service_inactive")
                page = system.get(port, "/")
                checks["homepage"] = page == (directory / "frontend/dist/index.html").read_bytes()
                parser = PageAssets()
                parser.feed(page.decode("utf-8"))
                if not checks["homepage"] or not any(path.endswith(".js") for path in parser.paths) or not any(path.endswith(".css") for path in parser.paths):
                    raise DeployError("assets_unavailable")
                for path in parser.paths:
                    local = directory / "frontend/dist" / path.lstrip("/")
                    if not local.is_file() or system.get(port, path) != local.read_bytes():
                        raise DeployError("assets_unavailable")
                checks["assets"] = True
                health = json.loads(system.get(port, "/healthz").decode("utf-8"))
                status = json.loads(system.get(port, "/api/status").decode("utf-8"))
                temperature = status.get("temperature_c")
                warning = warning or status.get("health") == "thermal_warning" or (isinstance(temperature, (int, float)) and temperature >= 78)
                checks["api"] = health.get("ok") is True
                camera = status.get("camera", {})
                model = status.get("model", {})
                checks["camera_connected"] = camera.get("connected") is True and camera.get("source") == "camera"
                checks["model_loaded"] = model.get("loaded") is True and model.get("backend") in ("opencv", "tensorrt")
                stamp = status.get("last_frame_ts")
                if not all(checks[name] for name in ("api", "camera_connected", "model_loaded")) or isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp):
                    raise DeployError("business_not_ready")
                if previous_frame is not None and stamp > previous_frame:
                    advances += 1
                elif previous_frame is not None and stamp < previous_frame:
                    advances = 0
                previous_frame = stamp
                checks["frame_advances"] = advances
                if advances >= 2 and system.monotonic() < deadline:
                    return checks, warning
            except (DeployError, OSError, ValueError, TypeError, AttributeError):
                advances = 0
                previous_frame = None
            system.sleep(min(2, max(0, deadline - system.monotonic())))
        raise DeployError("business_not_ready", checks, warning)
    finally:
        system.deadline = None


class Deployer:
    def __init__(self, layout, settings, system=None):
        self.layout = layout
        self.settings = settings
        self.system = system or System()

    @contextlib.contextmanager
    def locked(self, path, blocking=False):
        with path.open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BlockingIOError:
                raise DeployError("deployment_busy")
            yield

    def _find(self, identity):
        if JOB.fullmatch(identity):
            return self.layout.jobs / identity
        if not SHA.fullmatch(identity):
            raise DeployError("invalid_identity")
        candidates = []
        for directory in self.layout.jobs.iterdir():
            if JOB.fullmatch(directory.name) and (directory / "status.json").is_file():
                status = read_json(directory / "status.json")
                if status.get("commit") == identity:
                    candidates.append((status["created_at"], directory))
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate[0])[1]

    def status(self, identity=None):
        if identity is None:
            state = read_json(self.layout.state / "state.json") if (self.layout.state / "state.json").exists() else {}
            return {"current": self.layout.current_sha(), "previous": state.get("previous"), "phase": "idle", "http_port": self.settings["http_port"]}
        directory = self._find(identity)
        if directory is None or not (directory / "status.json").exists():
            return {"phase": "missing", "commit": identity if SHA.fullmatch(identity) else None}
        stored = read_json(directory / "status.json")
        public = {name: value for name, value in stored.items() if name in PUBLIC_FIELDS}
        for name in ("checks", "recovery_checks"):
            if name in public:
                public[name] = {key: value for key, value in public[name].items() if key in CHECK_FIELDS and isinstance(value, (int, bool))}
        return public

    def _new_job(self, commit, operation, digest=None):
        job = uuid.uuid4().hex
        directory = self.layout.jobs / job
        directory.mkdir(mode=0o700)
        report = {"job": job, "operation": operation, "commit": commit, "previous": self.layout.current_sha(),
                  "current": self.layout.current_sha(), "phase": "queued", "rollback": "not_needed", "created_at": time.time(),
                  "checks": {}, "temperature_warning": False, "http_port": self.settings["http_port"]}
        atomic_json(directory / "request.json", {"commit": commit, "operation": operation, "digest": digest})
        atomic_json(directory / "status.json", report)
        return directory, report

    def publish(self, commit, digest, stream):
        if not SHA.fullmatch(commit) or not DIGEST.fullmatch(digest):
            raise DeployError("invalid_identity")
        descriptor, name = tempfile.mkstemp(prefix="upload-", dir=str(self.layout.state))
        archive = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                size = 0
                while True:
                    chunk = stream.read(min(1024 * 1024, MAX_UPLOAD + 1 - size))
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        raise DeployError("archive_too_large")
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            validate_archive(archive, commit, digest)
            with self.locked(self.layout.state / "submit.lock", blocking=True):
                existing = self.status(commit)
                if existing["phase"] not in TERMINAL | {"missing"}:
                    request = read_json(self.layout.jobs / existing["job"] / "request.json")
                    if request["operation"] != "publish":
                        raise DeployError("deployment_busy")
                    if request["digest"] != digest:
                        raise DeployError("release_identity_conflict")
                    return existing
                directory, report = self._new_job(commit, "publish", digest)
                os.replace(str(archive), str(directory / "release.tar.gz"))
                self._launch(directory, report)
                return self.status(report["job"])
        finally:
            if archive.exists():
                archive.unlink()

    def _launch(self, directory, report):
        try:
            self.system.launch(report["job"])
        except DeployError as error:
            report.update(phase="failed", error=str(error), finished_at=time.time())
            atomic_json(directory / "status.json", report)
            raise

    def rollback(self, commit=None):
        if commit is None:
            commit = self.status().get("previous")
        if not commit or not SHA.fullmatch(commit):
            raise DeployError("no_rollback_target")
        directory = self.layout.releases / commit
        validate_installed(directory, commit)
        if not read_json(directory / ".release.json").get("successful_at"):
            raise DeployError("no_rollback_target")
        with self.locked(self.layout.state / "submit.lock", blocking=True):
            existing = self.status(commit)
            if existing["phase"] not in TERMINAL | {"missing"}:
                return existing
            job_directory, report = self._new_job(commit, "rollback")
            self._launch(job_directory, report)
            return self.status(report["job"])

    def _prepare(self, directory, request):
        commit = request["commit"]
        target = self.layout.releases / commit
        archive_path = directory / "release.tar.gz"
        manifest = validate_archive(archive_path, commit, request["digest"])
        if target.is_symlink():
            raise DeployError("release_not_valid")
        if target.exists():
            marker = target / ".release.json"
            if marker.is_file():
                metadata = read_json(marker)
                if metadata.get("bundle_sha256") == "legacy":
                    validate_installed(target, commit)
                    if read_json(target / "release-manifest.json") != manifest:
                        raise DeployError("release_identity_conflict")
                    metadata["bundle_sha256"] = request["digest"]
                    atomic_json(marker, metadata)
                if metadata.get("bundle_sha256") != request["digest"]:
                    raise DeployError("release_identity_conflict")
                validate_installed(target, commit)
                return target
            if commit == self.layout.current_sha():
                raise DeployError("release_not_valid")
            shutil.rmtree(str(target))
        staging = Path(tempfile.mkdtemp(prefix=".prepare-", dir=str(self.layout.releases)))
        try:
            with tarfile.open(str(archive_path), "r:gz") as archive:
                for member in archive:
                    destination = staging / member.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open("xb") as output:
                        shutil.copyfileobj(archive.extractfile(member), output)
                    destination.chmod(0o755 if member.name == "scripts/run_backend.sh" else 0o644)
            os.replace(str(staging), str(target))
        finally:
            if staging.exists():
                shutil.rmtree(str(staging))
        os.symlink(self.settings["models"], str(target / "models"))
        self.system.install(target, self.settings["python"])
        atomic_json(target / ".release.json", {"commit": manifest["commit"], "bundle_sha256": request["digest"]})
        return target

    def _restart_check(self, target):
        started = self.system.monotonic()
        self.system.restart()
        remaining = max(0, 180 - (self.system.monotonic() - started))
        return readiness(self.system, target, self.settings["http_port"], remaining)

    def apply(self, job):
        if not JOB.fullmatch(job):
            raise DeployError("invalid_identity")
        directory = self.layout.jobs / job
        request = read_json(directory / "request.json")
        report = read_json(directory / "status.json")
        if report["phase"] in TERMINAL:
            return
        switched = False
        previous = None
        try:
            with self.locked(self.layout.lock):
                try:
                    previous = self.layout.current_sha()
                    report.update(previous=previous, current=previous, phase="preparing")
                    atomic_json(directory / "status.json", report)
                    target = self.layout.releases / request["commit"]
                    if request["operation"] == "publish":
                        target = self._prepare(directory, request)
                    else:
                        validate_installed(target, request["commit"])
                    if previous != request["commit"]:
                        if previous:
                            validate_installed(self.layout.releases / previous, previous)
                        self.layout.switch(request["commit"])
                        switched = True
                    report.update(phase="checking", current=request["commit"])
                    atomic_json(directory / "status.json", report)
                    if switched:
                        checks, warning = self._restart_check(target)
                    else:
                        checks, warning = readiness(self.system, target, self.settings["http_port"])
                    report.update(phase="succeeded", checks=checks, temperature_warning=warning)
                    metadata = read_json(target / ".release.json")
                    metadata["successful_at"] = time.time()
                    atomic_json(target / ".release.json", metadata)
                    if switched:
                        atomic_json(self.layout.state / "state.json", {"current": request["commit"], "previous": previous})
                    try:
                        self._prune({request["commit"], previous, self.status().get("previous")})
                    except Exception:
                        report["maintenance_warning"] = "release_cleanup_failed"
                except Exception as error:
                    report.update(phase="failed", error=str(error) if isinstance(error, DeployError) else "internal_error")
                    if isinstance(error, DeployError):
                        report["checks"] = error.checks
                        report["temperature_warning"] = error.temperature_warning
                    if switched:
                        report["phase"] = "rolling_back"
                        try:
                            atomic_json(directory / "status.json", report)
                        except OSError:
                            pass
                        try:
                            if previous:
                                validate_installed(self.layout.releases / previous, previous)
                                self.layout.switch(previous)
                                checks, warning = self._restart_check(self.layout.releases / previous)
                                report.update(rollback="succeeded", current=previous, recovery_checks=checks,
                                              temperature_warning=report["temperature_warning"] or warning)
                            else:
                                self.system.stop()
                                self.layout.current.unlink()
                                report.update(rollback="no_previous_release", current=None)
                        except Exception:
                            try:
                                current = self.layout.current_sha()
                            except DeployError:
                                current = None
                            report.update(rollback="failed", error="rollback_failed", current=current)
                        report["phase"] = "failed"
        except DeployError as error:
            report.update(phase="failed", error=str(error))
        finally:
            report["finished_at"] = time.time()
            atomic_json(directory / "status.json", report)
            archive = directory / "release.tar.gz"
            if archive.exists():
                archive.unlink()

    def _prune(self, protected):
        successes = []
        for directory in self.layout.releases.iterdir():
            if SHA.fullmatch(directory.name) and not directory.is_symlink() and (directory / ".release.json").is_file():
                metadata = read_json(directory / ".release.json")
                if metadata.get("successful_at"):
                    successes.append((metadata["successful_at"], directory))
        successes.sort(key=lambda item: item[0], reverse=True)
        keep = protected | {directory.name for unused, directory in successes[:3]}
        for unused, directory in successes:
            if directory.name not in keep:
                shutil.rmtree(str(directory))


def trusted_path(path, directory=False):
    path = Path(path)
    if not path.is_absolute() or not path.exists() or (directory and not path.is_dir()):
        raise DeployError("unsafe_installation")
    for candidate in [path] + list(path.parents):
        stat = candidate.lstat()
        if candidate.is_symlink() or stat.st_uid != 0 or stat.st_mode & 0o022:
            raise DeployError("unsafe_installation")


def production_deployer():
    if os.geteuid() != 0:
        raise DeployError("root_required")
    os.umask(0o022)
    layout = Layout()
    for path in (layout.root, layout.releases, layout.state, layout.jobs, Path(HELPER).parent):
        trusted_path(path, directory=True)
    trusted_path(Path(HELPER))
    trusted_path(Path("/etc/cybervisual/deploy.json"))
    settings = read_json("/etc/cybervisual/deploy.json")
    if not isinstance(settings.get("http_port"), int) or not 1 <= settings["http_port"] <= 65535:
        raise DeployError("invalid_configuration")
    return Deployer(layout, settings)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command")
    publish = commands.add_parser("publish")
    publish.add_argument("commit")
    publish.add_argument("digest")
    status = commands.add_parser("status")
    status.add_argument("identity", nargs="?")
    rollback = commands.add_parser("rollback")
    rollback.add_argument("commit", nargs="?")
    worker = commands.add_parser("_apply")
    worker.add_argument("job")
    arguments = parser.parse_args()
    try:
        deployer = production_deployer()
        if arguments.command == "publish":
            result = deployer.publish(arguments.commit, arguments.digest, sys.stdin.buffer)
        elif arguments.command == "status":
            result = deployer.status(arguments.identity)
        elif arguments.command == "rollback":
            result = deployer.rollback(arguments.commit)
        elif arguments.command == "_apply":
            deployer.apply(arguments.job)
            result = deployer.status(arguments.job)
        else:
            parser.error("a command is required")
        print(json.dumps(result, sort_keys=True))
        return 1 if result.get("phase") == "failed" else 0
    except Exception as error:
        print(json.dumps({"phase": "failed", "error": str(error) if isinstance(error, DeployError) else "internal_error"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
