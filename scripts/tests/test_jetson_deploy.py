import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import jetson_deploy as deploy
import jetson_release as release


OLD = "1" * 40
NEW = "2" * 40
OTHER = "3" * 40


def payload_files(label="new"):
    return {
        "backend/cybervisual/__init__.py": b"",
        "backend/cybervisual/app.py": label.encode(),
        "backend/requirements.txt": b"Flask==2.0.3\n",
        "scripts/run_backend.sh": b"#!/bin/bash\nexit 0\n",
        "frontend/dist/index.html": b'<html><link rel="stylesheet" href="/assets/app.css"><script type="module" src="/assets/app.js"></script></html>',
        "frontend/dist/assets/app.js": label.encode(),
        "frontend/dist/assets/app.css": b"body{color:white}",
    }


def archive_bytes(sha=NEW, files=None, extra=None):
    files = files if files is not None else payload_files()
    manifest = {"format": 1, "commit": sha, "files": {
        name: hashlib.sha256(data).hexdigest() for name, data in files.items()
    }}
    members = dict(files)
    members["release-manifest.json"] = json.dumps(manifest).encode()
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, filename="", mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for name, data in members.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                member.mode = 0o644
                archive.addfile(member, io.BytesIO(data))
            if extra:
                member, data = extra
                archive.addfile(member, io.BytesIO(data) if data is not None else None)
    return output.getvalue()


class FakeSystem:
    def __init__(self, layout):
        self.layout = layout
        self.events = []
        self.elapsed = 0
        self.frame = 100
        self.running = True
        self.broken = set()
        self.dependencies_fail = False
        self.freeze_frames = False
        self.backend = "tensorrt"
        self.camera_source = "camera"
        self.missing_asset = False
        self.temperature = 82

    def launch(self, job):
        self.events.append(("launch", job))

    def install(self, directory, python):
        self.events.append(("install", directory.name))
        if self.dependencies_fail:
            raise deploy.DeployError("dependency_install_failed")
        (directory / ".venv/bin").mkdir(parents=True)
        (directory / ".venv/bin/python").write_text("isolated environment")

    def restart(self):
        self.events.append(("restart", self.layout.current.resolve().name))
        self.running = True

    def stop(self):
        self.events.append(("stop",))
        self.running = False

    def active(self):
        return self.running

    def monotonic(self):
        return self.elapsed

    def sleep(self, seconds):
        self.elapsed += seconds

    def get(self, port, path):
        current = self.layout.current.resolve()
        if path == "/healthz":
            return b'{"ok":true,"health":"running"}'
        if path == "/api/status":
            if not self.freeze_frames:
                self.frame += 1
            return json.dumps({
                "camera": {"connected": current.name not in self.broken, "source": self.camera_source},
                "model": {"loaded": True, "backend": self.backend},
                "last_frame_ts": self.frame, "temperature_c": self.temperature,
            }).encode()
        if self.missing_asset and path.endswith(".js"):
            raise deploy.DeployError("http_unavailable")
        name = "index.html" if path == "/" else path.lstrip("/")
        return (current / "frontend/dist" / name).read_bytes()


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.layout = deploy.Layout(root / "opt", root / "state")
        self.layout.prepare()
        self.persistent = root / "persistent"
        self.persistent.mkdir()
        for name in ("config.json", "camera.env", "model.engine", "device-id", "ptz-presets.json", "snapshot.jpg"):
            (self.persistent / name).write_bytes(b"private-existing-data")
        self.settings = {"python": "/usr/bin/python3", "http_port": 8000, "models": str(self.persistent)}
        self.system = FakeSystem(self.layout)
        self.deployer = deploy.Deployer(self.layout, self.settings, self.system)

    def submit(self, sha=NEW, data=None):
        data = data if data is not None else archive_bytes(sha)
        return self.deployer.publish(sha, hashlib.sha256(data).hexdigest(), io.BytesIO(data))

    def apply(self, sha=NEW):
        receipt = self.submit(sha)
        self.deployer.apply(receipt["job"])
        return self.deployer.status(receipt["job"])

    def baseline(self):
        result = self.apply(OLD)
        self.assertEqual(result["phase"], "succeeded")
        self.system.events.clear()

    def test_valid_release_has_isolated_venv_and_business_acceptance(self):
        result = self.apply()
        self.assertEqual(result["phase"], "succeeded")
        self.assertEqual(result["current"], NEW)
        self.assertGreaterEqual(result["checks"]["frame_advances"], 2)
        self.assertTrue(result["checks"]["assets"])
        self.assertTrue(result["temperature_warning"])
        self.assertTrue((self.layout.releases / NEW / ".venv/bin/python").exists())

    def test_checksum_rejected_before_launch(self):
        with self.assertRaisesRegex(deploy.DeployError, "checksum_mismatch"):
            self.deployer.publish(NEW, "0" * 64, io.BytesIO(archive_bytes()))
        self.assertEqual(self.system.events, [])
        self.assertFalse(self.layout.current.exists())

    def test_manifest_sha_cannot_substitute_another_commit(self):
        with self.assertRaisesRegex(deploy.DeployError, "commit_mismatch"):
            self.submit(NEW, archive_bytes(OTHER))
        self.assertEqual(self.system.events, [])

    def test_archive_traversal_links_duplicates_and_special_files_are_rejected(self):
        for name, kind in (("../../escaped", tarfile.REGTYPE), ("/etc/shadow", tarfile.REGTYPE),
                           ("frontend/dist/../escape", tarfile.REGTYPE), ("frontend/dist/link", tarfile.SYMTYPE),
                           ("frontend/dist/hard", tarfile.LNKTYPE), ("frontend/dist/fifo", tarfile.FIFOTYPE),
                           ("frontend/dist/index.html", tarfile.REGTYPE)):
            with self.subTest(name=name, kind=kind):
                member = tarfile.TarInfo(name)
                member.type = kind
                member.linkname = "/etc/shadow" if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE) else ""
                member.size = 0
                with self.assertRaises(deploy.DeployError):
                    self.submit(data=archive_bytes(extra=(member, b"" if kind == tarfile.REGTYPE else None)))
        self.assertEqual(self.system.events, [])

    def test_bundle_cannot_contain_config_models_data_or_deployer(self):
        for forbidden in ("backend/config.example.json", "models/model.engine", "captures/frame.jpg",
                          ".venv/bin/python", "scripts/deploy_jetson.sh", "frontend/dist/camera.env"):
            with self.subTest(forbidden=forbidden):
                files = payload_files()
                files[forbidden] = b"must not be delivered"
                with self.assertRaises(deploy.DeployError):
                    self.submit(data=archive_bytes(files=files))

    def test_manifest_hashes_must_match_contents(self):
        data = archive_bytes().replace(b"never-occurs", b"never-occurs")
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            files = {member.name: archive.extractfile(member).read() for member in archive.getmembers()}
        manifest = json.loads(files["release-manifest.json"])
        manifest["files"]["frontend/dist/assets/app.js"] = "0" * 64
        files["release-manifest.json"] = json.dumps(manifest).encode()
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            for name, content in files.items():
                member = tarfile.TarInfo(name)
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
        with self.assertRaisesRegex(deploy.DeployError, "file_checksum_mismatch"):
            self.submit(data=output.getvalue())

    def test_duplicate_release_does_not_reinstall_or_restart(self):
        with mock.patch("gzip.time.time", return_value=1700000000):
            self.baseline()
        with mock.patch("gzip.time.time", return_value=1700000060):
            result = self.apply(OLD)
        self.assertEqual(result["phase"], "succeeded")
        self.assertNotIn("install", [event[0] for event in self.system.events])
        self.assertNotIn("restart", [event[0] for event in self.system.events])

    def test_first_ci_publish_can_recognize_an_identical_legacy_baseline(self):
        self.baseline()
        marker = self.layout.releases / OLD / ".release.json"
        metadata = json.loads(marker.read_text())
        metadata["bundle_sha256"] = "legacy"
        marker.write_text(json.dumps(metadata))
        result = self.apply(OLD)
        self.assertEqual(result["phase"], "succeeded")
        self.assertFalse(any(event[0] in ("install", "restart") for event in self.system.events))
        result = self.submit(OLD, archive_bytes(OLD, payload_files("different")))
        self.deployer.apply(result["job"])
        self.assertEqual(self.deployer.status(result["job"])["error"], "release_identity_conflict")

    def test_dependency_failure_leaves_old_link_service_and_venv_untouched(self):
        self.baseline()
        self.system.dependencies_fail = True
        result = self.apply()
        self.assertEqual(result["error"], "dependency_install_failed")
        self.assertEqual(result["phase"], "failed")
        self.assertEqual(self.layout.current.resolve().name, OLD)
        self.assertFalse(any(event[0] == "restart" for event in self.system.events))
        self.assertEqual((self.layout.releases / OLD / ".venv/bin/python").read_text(), "isolated environment")

    def test_unready_camera_rolls_back_and_checks_recovery(self):
        self.baseline()
        self.system.broken.add(NEW)
        result = self.apply()
        self.assertEqual(result["phase"], "failed")
        self.assertEqual(result["rollback"], "succeeded")
        self.assertEqual(result["current"], OLD)
        self.assertTrue(result["recovery_checks"]["camera_connected"])
        self.assertEqual([event for event in self.system.events if event[0] == "restart"], [("restart", NEW), ("restart", OLD)])

    def test_failed_rollback_is_distinct(self):
        self.baseline()
        self.system.broken.update((OLD, NEW))
        result = self.apply()
        self.assertEqual(result["rollback"], "failed")
        self.assertEqual(result["error"], "rollback_failed")

    def test_diagnostic_write_failure_cannot_prevent_restoring_previous_release(self):
        self.baseline()
        self.system.broken.add(NEW)
        original = deploy.atomic_json

        def write(path, value):
            if Path(path).name == "status.json" and value.get("phase") == "rolling_back":
                raise OSError("diagnostic volume temporarily unavailable")
            original(path, value)

        with mock.patch.object(deploy, "atomic_json", side_effect=write):
            result = self.apply()
        self.assertEqual(self.layout.current.resolve().name, OLD)
        self.assertEqual(result["rollback"], "succeeded")

    def test_intake_deduplicates_active_job_but_rejects_different_bytes_for_same_sha(self):
        receipt = self.submit()
        self.assertEqual(self.submit()["job"], receipt["job"])
        with self.assertRaisesRegex(deploy.DeployError, "release_identity_conflict"):
            self.submit(data=archive_bytes(files=payload_files("other-content")))
        self.assertEqual(len(self.system.events), 1)

    def test_first_install_failure_stops_service_and_retains_diagnostics(self):
        self.system.broken.add(NEW)
        result = self.apply()
        self.assertEqual(result["rollback"], "no_previous_release")
        self.assertTrue(result["temperature_warning"])
        self.assertFalse(self.system.running)
        self.assertFalse(self.layout.current.exists())
        self.assertEqual(self.deployer.status(NEW)["job"], result["job"])

    def test_static_frames_missing_assets_and_mock_backend_never_pass(self):
        for option, value in (("freeze_frames", True), ("missing_asset", True), ("backend", "mock"),
                              ("camera_source", "synthetic")):
            with self.subTest(option=option):
                setattr(self.system, option, value)
                result = self.apply()
                self.assertEqual(result["phase"], "failed")
                setattr(self.system, option, {"backend": "tensorrt", "camera_source": "camera"}.get(option, False))

    def test_local_transaction_lock_prevents_switch(self):
        import fcntl
        self.baseline()
        receipt = self.submit()
        with self.layout.lock.open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.deployer.apply(receipt["job"])
        self.assertEqual(self.deployer.status(receipt["job"])["error"], "deployment_busy")
        self.assertEqual(self.layout.current.resolve().name, OLD)
        self.assertFalse(any(event[0] == "restart" for event in self.system.events))

    def test_publication_returns_before_detached_worker_and_survives_client_disconnect(self):
        receipt = self.submit()
        self.assertEqual(receipt["phase"], "queued")
        self.assertFalse(self.layout.current.exists())
        del receipt
        job = self.deployer.status(NEW)["job"]
        deploy.Deployer(self.layout, self.settings, self.system).apply(job)
        self.assertEqual(self.deployer.status(NEW)["phase"], "succeeded")

    def test_detached_process_completes_after_upload_client_is_killed(self):
        data = archive_bytes()
        archive = Path(self.temporary.name) / "incoming.tar.gz"
        archive.write_bytes(data)
        worker = (
            "import sys,time; from pathlib import Path; "
            "sys.path[:0]=%r; import jetson_deploy as deploy; from test_jetson_deploy import FakeSystem; "
            "layout=deploy.Layout(Path(%r),Path(%r)); time.sleep(0.3); "
            "deploy.Deployer(layout,%r,FakeSystem(layout)).apply(sys.argv[1])"
        ) % ([str(SCRIPTS), str(SCRIPTS / "tests")], str(self.layout.root), str(self.layout.state), self.settings)
        parent = "\n".join([
            "import sys,subprocess,time; from pathlib import Path",
            "sys.path[:0]=%r" % [str(SCRIPTS), str(SCRIPTS / "tests")],
            "import jetson_deploy as deploy; from test_jetson_deploy import FakeSystem",
            "layout=deploy.Layout(Path(%r),Path(%r))" % (str(self.layout.root), str(self.layout.state)),
            "class Detached(FakeSystem):",
            "    def launch(self,job):",
            "        subprocess.Popen([sys.executable,'-c',%r,job],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,close_fds=True)" % worker,
            "with open(%r,'rb') as stream:" % str(archive),
            "    receipt=deploy.Deployer(layout,%r,Detached(layout)).publish(%r,%r,stream)" % (self.settings, NEW, hashlib.sha256(data).hexdigest()),
            "print(receipt['job'],flush=True)",
            "time.sleep(30)",
        ])
        process = subprocess.Popen([sys.executable, "-c", parent], stdout=subprocess.PIPE, text=True)
        try:
            job = process.stdout.readline().strip()
            self.assertRegex(job, r"^[0-9a-f]{32}$")
        finally:
            process.kill()
            process.wait(timeout=5)
            process.stdout.close()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and self.deployer.status(job)["phase"] not in deploy.TERMINAL:
            time.sleep(0.05)
        self.assertEqual(self.deployer.status(job)["phase"], "succeeded")

    def test_cleanup_failure_must_not_undo_a_healthy_release(self):
        self.baseline()
        with mock.patch.object(self.deployer, "_prune", side_effect=OSError("disk busy")):
            result = self.apply()
        self.assertEqual(result["phase"], "succeeded")
        self.assertEqual(result["current"], NEW)

    def test_configuration_models_identity_presets_and_snapshots_unchanged(self):
        before = {path.name: path.read_bytes() for path in self.persistent.iterdir()}
        self.baseline()
        self.apply()
        self.system.broken.add(OTHER)
        self.apply(OTHER)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.persistent.iterdir()})
        self.assertEqual((self.layout.releases / NEW / "models").resolve(), self.persistent.resolve())

    def test_manual_rollback_restores_successful_venv(self):
        self.baseline()
        self.apply()
        receipt = self.deployer.rollback(OLD)
        self.deployer.apply(receipt["job"])
        result = self.deployer.status(receipt["job"])
        self.assertEqual(result["phase"], "succeeded")
        self.assertEqual(result["current"], OLD)
        self.assertEqual(result["previous"], NEW)

    def test_retention_keeps_three_successes_current_and_previous(self):
        for number in range(1, 6):
            self.apply(str(number) * 40)
        self.assertEqual({path.name for path in self.layout.releases.iterdir()}, {str(number) * 40 for number in (3, 4, 5)})

    def test_diagnostics_export_only_allowlisted_fields(self):
        result = self.apply()
        report = self.layout.jobs / result["job"] / "status.json"
        stored = json.loads(report.read_text())
        stored.update({"environment": "secret", "last_error": "password=secret", "model": "secret", "frame": "secret"})
        report.write_text(json.dumps(stored))
        public = json.dumps(self.deployer.status(result["job"]))
        self.assertNotIn("secret", public)


class GateAndPackagingTests(unittest.TestCase):
    def test_interrupted_workflow_summary_does_not_claim_worker_was_cancelled(self):
        with tempfile.TemporaryDirectory() as directory:
            diagnostics = Path(directory) / "diagnostics"
            summary = Path(directory) / "summary.md"
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary), "DEPLOY_JOB_STATUS": "failure"}):
                for unused in range(3):
                    release.record("jetson.example.ts.net", NEW, {"phase": "checking", "job": "a" * 32}, diagnostics)
                self.assertFalse(summary.exists())
                with mock.patch.object(sys, "argv", ["jetson_release.py", "summarize", "--sha", NEW, "--diagnostics", str(diagnostics)]):
                    self.assertEqual(release.main(), 0)
            result = json.loads((diagnostics / "status.json").read_text())
            self.assertEqual(result["phase"], "unknown")
            self.assertEqual(result["error"], "workflow_interrupted_worker_not_cancelled")
            self.assertEqual(summary.read_text().count("## Jetson deployment"), 1)

    def test_only_enabled_main_push_or_manual_with_all_ci_success_is_eligible(self):
        jobs = {name: {"result": "success"} for name in ("linux-camera", "dashboard", "deployment-tests")}
        for event in ("push", "workflow_dispatch"):
            self.assertTrue(release.eligible(event, "refs/heads/main", "Arasaka-Academy/CyberVisual", "true", jobs))
        for event, ref, repository, enabled in (
            ("pull_request", "refs/heads/main", "Arasaka-Academy/CyberVisual", "true"),
            ("workflow_dispatch", "refs/heads/other", "Arasaka-Academy/CyberVisual", "true"),
            ("push", "refs/heads/main", "fork/CyberVisual", "true"),
            ("push", "refs/heads/main", "Arasaka-Academy/CyberVisual", ""),
        ):
            self.assertFalse(release.eligible(event, ref, repository, enabled, jobs))
        for result in ("failure", "cancelled", "skipped", ""):
            jobs["dashboard"]["result"] = result
            self.assertFalse(release.eligible("push", "refs/heads/main", "Arasaka-Academy/CyberVisual", "true", jobs))

    def test_outdated_sha_and_unverifiable_main_fail_closed(self):
        self.assertTrue(release.latest_main(NEW, NEW + "\trefs/heads/main\n"))
        self.assertFalse(release.latest_main(OLD, NEW + "\trefs/heads/main\n"))
        for value in ("", "broken", NEW + "\trefs/heads/other\n"):
            self.assertFalse(release.latest_main(NEW, value))

    def test_packaging_uses_only_tracked_allowed_payload_at_exact_sha(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in payload_files().items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
            sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            (root / "models").mkdir()
            (root / "models/secret.engine").write_bytes(b"secret")
            output = root / "release.tar.gz"
            release.build_package(root, sha, output)
            manifest = deploy.validate_archive(output, sha, hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(set(manifest["files"]), set(payload_files()))
            (root / "frontend/dist/assets/app.js").write_bytes(b"not tested")
            with self.assertRaises(deploy.DeployError):
                release.build_package(root, sha, output)

    def test_systemd_worker_has_no_ssh_parent_dependency_or_shell(self):
        with mock.patch("jetson_deploy.subprocess.run") as command:
            deploy.System().launch("a" * 32)
        arguments = command.call_args[0][0]
        self.assertEqual(arguments[0], "/usr/bin/systemd-run")
        self.assertIn("--no-block", arguments)
        self.assertNotIn("--wait", arguments)
        self.assertNotIn("--scope", arguments)
        self.assertIn("/usr/local/lib/cybervisual-deploy/jetson_deploy.py", arguments)
        self.assertFalse(command.call_args[1].get("shell", False))


if __name__ == "__main__":
    unittest.main()
