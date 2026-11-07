import ast
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jetson_bootstrap as bootstrap
from jetson_deploy import DeployError


class BootstrapTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("visudo"), "visudo is available on Linux CI and prepared Jetson hosts")
    def test_exact_sudoers_rule_passes_the_system_parser(self):
        tree = ast.parse(Path(bootstrap.__file__).read_text())
        definitions = [node for node in ast.walk(tree) if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "sudoers" for target in node.targets)]
        self.assertEqual(len(definitions), 1)
        rule = ast.literal_eval(definitions[0].value)
        result = subprocess.run([shutil.which("visudo"), "--check", "--file", "-"], input=rule.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.installation = self.root / "opt"
        self.installation.mkdir()
        self.persistent = self.root / "persistent"
        self.persistent.mkdir()
        self.config = self.persistent / "config.json"
        self.config.write_text(json.dumps({"source": "camera", "detector_backend": "auto"}))
        self.model = self.persistent / "model.engine"
        self.model.write_bytes(b"existing engine")
        self.environment = self.persistent / "camera.env"
        self.values = {
            "CYBERVISUAL_CONFIG": str(self.config), "CYBERVISUAL_MODEL_PATH": str(self.model),
            "CYBERVISUAL_STATE_DIR": str(self.persistent), "CYBERVISUAL_CAPTURE_DIR": str(self.persistent),
            "CYBERVISUAL_PORT": "8000", "CYBERVISUAL_SOURCE": "camera", "CYBERVISUAL_DETECTOR": "auto",
        }
        self.save_environment()

    def save_environment(self):
        self.environment.write_text("\n".join(name + "=" + value for name, value in self.values.items()) + "\n")

    def test_environment_parser_never_executes_shell_and_preserves_quoted_credentials(self):
        result = bootstrap.parse_environment('CYBERVISUAL_PASSWORD="literal $HOME ; # password"\n')
        self.assertEqual(result["CYBERVISUAL_PASSWORD"], "literal $HOME ; # password")
        for text in ("export X=y", "PYTHON=/tmp/untrusted", "CYBERVISUAL_PORT=1\nCYBERVISUAL_PORT=2", "CYBERVISUAL_FRONTEND_DIST=/tmp"):
            with self.assertRaises(DeployError):
                bootstrap.parse_environment(text)

    def test_persistent_paths_are_explicit_and_not_relocated(self):
        before = {path.name: path.read_bytes() for path in self.persistent.iterdir()}
        result = bootstrap.runtime_settings(self.environment, self.installation, 8000)
        self.assertEqual(result["config"], str(self.config))
        self.assertEqual(result["models"], str(self.persistent))
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.persistent.iterdir()})

    def test_missing_relative_release_scoped_and_mock_paths_fail_closed(self):
        for name, value in (("CYBERVISUAL_MODEL_PATH", "models/model.engine"),
                            ("CYBERVISUAL_CONFIG", str(self.root / "missing.json")),
                            ("CYBERVISUAL_STATE_DIR", str(self.installation / "releases")),
                            ("CYBERVISUAL_DETECTOR", "mock"), ("CYBERVISUAL_SOURCE", "synthetic")):
            with self.subTest(name=name, value=value):
                previous = self.values[name]
                self.values[name] = value
                self.save_environment()
                with self.assertRaises(DeployError):
                    bootstrap.runtime_settings(self.environment, self.installation, 8000)
                self.values[name] = previous

    def test_http_port_must_match_device_configuration(self):
        with self.assertRaisesRegex(DeployError, "http_port_mismatch"):
            bootstrap.runtime_settings(self.environment, self.installation, 9000)

    def test_runtime_environment_file_itself_must_be_persistent(self):
        environment = self.installation / "releases" / ("1" * 40) / "camera.env"
        environment.parent.mkdir(parents=True)
        environment.write_bytes(self.environment.read_bytes())
        with self.assertRaisesRegex(DeployError, "release_scoped_persistence"):
            bootstrap.runtime_settings(environment, self.installation, 8000)

    def test_migration_cannot_add_new_hardware_overrides(self):
        settings = bootstrap.runtime_settings(self.environment, self.installation, 8000)
        candidate = dict(self.values, CYBERVISUAL_CAMERA_INDEX="9")
        with self.assertRaisesRegex(DeployError, "legacy_environment_not_preserved"):
            bootstrap.verify_migration(self.legacy_unit(), self.installation, candidate, settings)

    def legacy_unit(self):
        return "\n".join([
            "[Service]", "WorkingDirectory=" + str(self.installation),
            "ExecStart=" + str(self.installation / "scripts/run_backend.sh"),
            "EnvironmentFile=" + str(self.environment),
        ])

    def test_legacy_configuration_and_hardware_environment_must_match(self):
        settings = bootstrap.runtime_settings(self.environment, self.installation, 8000)
        result = bootstrap.verify_migration(self.legacy_unit(), self.installation, self.values, settings)
        self.assertEqual(result["working_directory"], str(self.installation))
        self.assertEqual(result["models"], str(self.installation / "models"))
        unit = self.legacy_unit() + "\nEnvironment=CYBERVISUAL_CAMERA_FPS=25\n"
        with self.assertRaisesRegex(DeployError, "legacy_environment_not_preserved"):
            bootstrap.verify_migration(unit, self.installation, self.values, settings)

    def test_unknown_legacy_launchers_or_service_options_require_manual_review(self):
        settings = bootstrap.runtime_settings(self.environment, self.installation, 8000)
        for text in (self.legacy_unit().replace("scripts/run_backend.sh", "custom.sh"),
                     self.legacy_unit() + "\nExecStartPre=/usr/local/bin/custom\n",
                     self.legacy_unit() + "\nUser=nvidia\n"):
            with self.assertRaises(DeployError):
                bootstrap.verify_migration(text, self.installation, self.values, settings)

    @contextmanager
    def sandbox_prepare(self, on_install=None):
        layout = bootstrap.Layout(self.installation, self.root / "deploy-state")
        settings_path = self.root / "etc/deploy.json"
        unit_path = self.root / "etc/cybervisual.service"
        options = SimpleNamespace(apply=False, runtime_env=str(self.environment), http_port=8000, python="/usr/bin/python3",
                                  confirm_migration=False, migrate_from=None, legacy_sha=None)
        commands = []
        original_install = bootstrap.install_file

        def command(arguments, timeout=30):
            commands.append(arguments)
            if arguments[:3] == ["systemctl", "show", "cybervisual.service"]:
                if "--property=DropInPaths" in arguments:
                    return ""
                return str(unit_path) if unit_path.exists() else ""
            if arguments[:2] == ["systemctl", "cat"]:
                return unit_path.read_text()
            return ""

        def install(content, destination, mode):
            if on_install:
                on_install(layout, Path(destination))
            if str(destination).startswith(("/usr/local/", "/etc/sudoers.d/")):
                destination = self.root / "sandbox" / str(destination).lstrip("/")
            original_install(content, destination, mode)

        account = SimpleNamespace(pw_uid=987, pw_gid=987, pw_dir="/var/lib/cybervisual-deploy-user", pw_shell="/bin/bash")
        with mock.patch.object(bootstrap, "Layout", return_value=layout), mock.patch.object(bootstrap, "SETTINGS", settings_path), \
                mock.patch.object(bootstrap, "UNIT", unit_path), mock.patch.object(bootstrap, "prerequisites", return_value=[]), \
                mock.patch.object(bootstrap, "DEPLOY_HELPER", self.root / "sandbox/usr/local/lib/cybervisual-deploy/jetson_deploy.py", create=True), \
                mock.patch.object(bootstrap, "DEPLOY_ENTRY", self.root / "sandbox/usr/local/sbin/cybervisual-deploy", create=True), \
                mock.patch.object(bootstrap, "SUDOERS", self.root / "sandbox/etc/sudoers.d/cybervisual-deploy", create=True), \
                mock.patch.object(bootstrap, "trusted_path"), mock.patch.object(bootstrap, "command", side_effect=command), \
                mock.patch.object(bootstrap, "install_file", side_effect=install), mock.patch.object(bootstrap.os, "geteuid", return_value=0), \
                mock.patch.object(bootstrap.pwd, "getpwnam", return_value=account), mock.patch.object(bootstrap.os, "getgrouplist", return_value=[987]):
            yield SimpleNamespace(layout=layout, settings=settings_path, unit=unit_path, options=options, commands=commands)

    def test_default_check_is_read_only_and_explicit_apply_is_repeatable(self):
        before = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        with self.sandbox_prepare() as sandbox:
            options = sandbox.options
            bootstrap.prepare(options)
            after = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
            self.assertEqual(before, after)
            self.assertFalse(sandbox.layout.state.exists())
            options.apply = True
            bootstrap.prepare(options)
            settings = sandbox.settings.read_bytes()
            unit = sandbox.unit.read_bytes()
            bootstrap.prepare(options)
            self.assertEqual(sandbox.settings.read_bytes(), settings)
            self.assertEqual(sandbox.unit.read_bytes(), unit)
        self.assertEqual(before[str(self.environment.relative_to(self.root))], self.environment.read_bytes())
        self.assertFalse(any(arguments[:2] in (["systemctl", "start"], ["systemctl", "restart"]) for arguments in sandbox.commands))
        sudoers = (self.root / "sandbox/etc/sudoers.d/cybervisual-deploy").read_text()
        self.assertNotIn("NOPASSWD: ALL", sudoers)
        self.assertIn("NOSETENV: /usr/local/sbin/cybervisual-deploy", sudoers)

    def test_bootstrap_excludes_new_publications_while_replacing_the_deployer(self):
        unlocked = []

        def check_submission_lock(layout, destination):
            with (layout.state / "submit.lock").open("a") as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return
            unlocked.append(str(destination))

        with self.sandbox_prepare(on_install=check_submission_lock) as sandbox:
            sandbox.options.apply = True
            bootstrap.prepare(sandbox.options)
        self.assertEqual(unlocked, [])

    def test_failed_first_preparation_restores_files_and_can_be_retried(self):
        with self.sandbox_prepare() as sandbox:
            sandbox.options.apply = True
            original = bootstrap.atomic_json

            def write(path, value):
                if Path(path) == sandbox.settings:
                    raise OSError("fixture settings write failed")
                original(path, value)

            with mock.patch.object(bootstrap, "atomic_json", side_effect=write):
                with self.assertRaises(OSError):
                    bootstrap.prepare(sandbox.options)
            self.assertFalse(sandbox.unit.exists())
            self.assertFalse(sandbox.settings.exists())
            self.assertFalse((self.root / "sandbox/etc/sudoers.d/cybervisual-deploy").exists())
            self.assertFalse((self.root / "sandbox/usr/local/sbin/cybervisual-deploy").exists())
            bootstrap.prepare(sandbox.options)
            self.assertTrue(sandbox.settings.is_file())

    def test_failed_upgrade_restores_the_existing_deployer_unit_and_settings(self):
        with self.sandbox_prepare() as sandbox:
            sandbox.options.apply = True
            bootstrap.prepare(sandbox.options)
            entry = self.root / "sandbox/usr/local/sbin/cybervisual-deploy"
            entry.write_bytes(b"previous fixed entry")
            before = {path: path.read_bytes() for path in (entry, sandbox.unit, sandbox.settings)}
            with mock.patch.object(bootstrap, "atomic_json", side_effect=OSError("fixture settings write failed")):
                with self.assertRaises(OSError):
                    bootstrap.prepare(sandbox.options)
            self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_failed_migration_restores_original_unit_link_and_release_state(self):
        with self.sandbox_prepare() as sandbox:
            sandbox.options.apply = True
            sandbox.options.confirm_migration = True
            sandbox.options.migrate_from = str(self.installation)
            sandbox.options.legacy_sha = "1" * 40
            sandbox.unit.parent.mkdir(parents=True)
            old_unit = self.legacy_unit()
            sandbox.unit.write_text(old_unit)
            original = bootstrap.atomic_json

            def baseline(root, commit, layout, settings):
                (layout.releases / commit).mkdir()
                layout.switch(commit)
                original(layout.state / "state.json", {"current": commit, "previous": None})

            def write(path, value):
                if Path(path) == sandbox.settings:
                    raise OSError("fixture settings write failed")
                original(path, value)

            with mock.patch.object(bootstrap, "verify_legacy_payload"), \
                    mock.patch.object(bootstrap, "legacy_baseline", side_effect=baseline), \
                    mock.patch.object(bootstrap, "atomic_json", side_effect=write):
                with self.assertRaises(OSError):
                    bootstrap.prepare(sandbox.options)
            self.assertEqual(sandbox.unit.read_text(), old_unit)
            self.assertFalse(sandbox.layout.current.is_symlink())
            self.assertFalse((sandbox.layout.state / "state.json").exists())
            self.assertFalse((sandbox.layout.releases / sandbox.options.legacy_sha).exists())
            with mock.patch.object(bootstrap, "verify_legacy_payload"), \
                    mock.patch.object(bootstrap, "legacy_baseline", side_effect=baseline):
                bootstrap.prepare(sandbox.options)
            self.assertEqual(sandbox.layout.current_sha(), sandbox.options.legacy_sha)


if __name__ == "__main__":
    unittest.main()
