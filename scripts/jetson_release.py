import argparse
import gzip
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import time

from jetson_deploy import DeployError, SHA, REQUIRED, allowed_payload, atomic_json, file_digest, validate_archive


REPOSITORY = "Arasaka-Academy/CyberVisual"
CI_JOBS = ("linux-camera", "dashboard", "deployment-tests")
PAYLOAD_ROOTS = ("backend/cybervisual", "backend/requirements.txt", "scripts/run_backend.sh", "frontend/dist")
HOST = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?$")


def eligible(event, ref, repository, enabled, jobs):
    return (event in ("push", "workflow_dispatch") and ref == "refs/heads/main" and repository == REPOSITORY
            and enabled == "true" and all(jobs.get(name, {}).get("result") == "success" for name in CI_JOBS))


def latest_main(commit, remote_output):
    return bool(SHA.fullmatch(commit) and remote_output.strip() == commit + "\trefs/heads/main")


def verified_main(commit):
    try:
        result = subprocess.run(["git", "ls-remote", "--exit-code", "origin", "refs/heads/main"],
                                check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30)
        return latest_main(commit, result.stdout.decode("ascii"))
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise DeployError("main_verification_failed")


def git_output(root, *arguments):
    try:
        return subprocess.check_output(["git", "-C", str(root)] + list(arguments), stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        raise DeployError("git_verification_failed")


def build_package(root, commit, output):
    root = Path(root)
    output = Path(output)
    if not SHA.fullmatch(commit) or git_output(root, "rev-parse", "HEAD").decode().strip() != commit:
        raise DeployError("commit_mismatch")
    if git_output(root, "status", "--porcelain", "--untracked-files=all", "--", *PAYLOAD_ROOTS):
        raise DeployError("untested_payload_changes")
    names = git_output(root, "ls-files", "-z", "--", *PAYLOAD_ROOTS).decode().split("\0")
    names = sorted(name for name in names if name and allowed_payload(name))
    if not REQUIRED.issubset(names):
        raise DeployError("incomplete_payload")
    files = {}
    for name in names:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise DeployError("unsafe_payload")
        files[name] = file_digest(path)
    manifest = {"format": 1, "commit": commit, "files": files}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as destination:
        with gzip.GzipFile(fileobj=destination, filename="", mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for name in names + ["release-manifest.json"]:
                    data = json.dumps(manifest, sort_keys=True).encode() if name == "release-manifest.json" else (root / name).read_bytes()
                    member = tarfile.TarInfo(name)
                    member.size = len(data)
                    member.mode = 0o755 if name == "scripts/run_backend.sh" else 0o644
                    archive.addfile(member, io.BytesIO(data))
    digest = file_digest(output)
    validate_archive(output, commit, digest)
    output.with_suffix(output.suffix + ".sha256").write_text(digest + "  " + output.name + "\n")
    return manifest


def remote(host, command, stream=None, timeout=45):
    if not HOST.fullmatch(host):
        raise DeployError("invalid_target")
    try:
        result = subprocess.run(["tailscale", "ssh", "--", "cybervisual-deploy@" + host, "sudo", "-n",
                                 "/usr/local/sbin/cybervisual-deploy"] + command,
                                stdin=stream if stream is not None else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
        if len(result.stdout) > 32768:
            raise DeployError("invalid_remote_report")
        report = json.loads(result.stdout.decode("utf-8"))
        if not isinstance(report, dict) or report.get("phase") not in ("queued", "preparing", "checking", "rolling_back", "succeeded", "failed", "missing", "idle"):
            raise DeployError("invalid_remote_report")
        return report
    except (OSError, subprocess.SubprocessError, ValueError, UnicodeError):
        raise DeployError("connection_interrupted")


def record(host, commit, report, diagnostics, summarize=False):
    diagnostics = Path(diagnostics)
    diagnostics.mkdir(parents=True, exist_ok=True)
    allowed = {"job", "operation", "commit", "previous", "current", "phase", "error", "rollback", "checks",
               "recovery_checks", "temperature_warning", "created_at", "finished_at", "http_port", "maintenance_warning"}
    public = {name: value for name, value in report.items() if name in allowed}
    public.update(target=host, commit=commit)
    atomic_json(diagnostics / "status.json", public)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and summarize:
        with open(summary, "a") as handle:
            handle.write("\n## Jetson deployment\n\n")
            for label, value in (("Target", host), ("Commit", commit), ("Previous", public.get("previous")),
                                 ("Current", public.get("current")), ("Result", public.get("phase")),
                                 ("Error", public.get("error")), ("Rollback", public.get("rollback")),
                                 ("Maintenance", public.get("maintenance_warning")),
                                 ("Temperature warning", public.get("temperature_warning", False))):
                handle.write("- %s: `%s`\n" % (label, str(value).replace("`", "").replace("\n", " ")))
            for label, key in (("Business checks", "checks"), ("Recovery checks", "recovery_checks")):
                handle.write("- %s: `%s`\n" % (label, json.dumps(public.get(key, {}), sort_keys=True)))


def deploy_release(host, port, commit, archive, diagnostics):
    if not HOST.fullmatch(host) or not SHA.fullmatch(commit) or not 1 <= port <= 65535:
        raise DeployError("invalid_target")
    archive = Path(archive)
    digest = file_digest(archive)
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    if not checksum.is_file() or checksum.read_text().strip() != digest + "  " + archive.name:
        raise DeployError("checksum_mismatch")
    validate_archive(archive, commit, digest)
    if not verified_main(commit):
        record(host, commit, {"phase": "skipped", "error": "outdated_main"}, diagnostics)
        return 0
    status = remote(host, ["status"])
    if status.get("http_port") != port:
        raise DeployError("http_port_mismatch")
    report = {}
    deadline = time.monotonic() + 1500
    submissions = 0
    while time.monotonic() < deadline:
        try:
            if not report or (report.get("phase") == "missing" and submissions < 2):
                if not verified_main(commit):
                    record(host, commit, {"phase": "skipped", "error": "outdated_main"}, diagnostics)
                    return 0
                submissions += 1
                with archive.open("rb") as stream:
                    report = remote(host, ["publish", commit, digest], stream, timeout=180)
            else:
                report = remote(host, ["status", report.get("job", commit)])
            record(host, commit, report, diagnostics)
            if report.get("phase") == "succeeded":
                return 0
            if report.get("phase") == "failed":
                return 1
        except DeployError as error:
            if str(error) != "connection_interrupted":
                raise
            report = {"phase": "missing"}
            try:
                report = remote(host, ["status", commit])
            except DeployError:
                pass
        time.sleep(5)
    record(host, commit, dict(report, phase="unknown", error="client_timeout_worker_not_cancelled"), diagnostics)
    return 1


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command")
    package = commands.add_parser("package")
    package.add_argument("--sha", required=True)
    package.add_argument("--output", required=True)
    gate = commands.add_parser("gate")
    gate.add_argument("--sha", default=os.environ.get("GITHUB_SHA", ""))
    deploy = commands.add_parser("deploy")
    deploy.add_argument("--sha", required=True)
    deploy.add_argument("--archive", required=True)
    deploy.add_argument("--host", default=os.environ.get("JETSON_HOST") or "nvidia-jetson-nano.civet-beta.ts.net")
    deploy.add_argument("--port", type=int, default=int(os.environ.get("JETSON_HTTP_PORT") or "8000"))
    deploy.add_argument("--diagnostics", default="jetson-diagnostics")
    summary = commands.add_parser("summarize")
    summary.add_argument("--sha", required=True)
    summary.add_argument("--diagnostics", required=True)
    arguments = parser.parse_args()
    try:
        if arguments.command == "package":
            build_package(Path(__file__).resolve().parents[1], arguments.sha, arguments.output)
        elif arguments.command == "gate":
            jobs = json.loads(os.environ.get("CI_RESULTS", "{}"))
            allowed = eligible(os.environ.get("GITHUB_EVENT_NAME"), os.environ.get("GITHUB_REF"),
                               os.environ.get("GITHUB_REPOSITORY"), os.environ.get("JETSON_DEPLOY_ENABLED"), jobs)
            latest = allowed and verified_main(arguments.sha)
            with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
                handle.write("latest=%s\n" % str(latest).lower())
            if not latest:
                record(os.environ.get("JETSON_HOST") or "nvidia-jetson-nano.civet-beta.ts.net", arguments.sha,
                       {"phase": "skipped", "error": "outdated_main" if allowed else "deployment_not_allowed"},
                       os.environ.get("JETSON_DIAGNOSTICS", "jetson-diagnostics"))
        elif arguments.command == "deploy":
            return deploy_release(arguments.host, arguments.port, arguments.sha, arguments.archive, arguments.diagnostics)
        elif arguments.command == "summarize":
            path = Path(arguments.diagnostics) / "status.json"
            report = json.loads(path.read_text()) if path.is_file() else {
                "phase": "failed", "error": "workflow_stage_failed", "rollback": "unknown",
                "checks": {}, "previous": None, "current": None,
            }
            if report.get("phase") in ("queued", "preparing", "checking", "rolling_back") and os.environ.get("DEPLOY_JOB_STATUS") in ("failure", "cancelled"):
                report.update(phase="unknown", error="workflow_interrupted_worker_not_cancelled", rollback="unknown")
            record(os.environ.get("JETSON_HOST") or "nvidia-jetson-nano.civet-beta.ts.net", arguments.sha,
                   report, arguments.diagnostics, summarize=True)
        else:
            parser.error("a command is required")
        return 0
    except Exception as error:
        code = str(error) if isinstance(error, DeployError) else "client_internal_error"
        if arguments.command == "deploy":
            record(arguments.host, arguments.sha, {"phase": "failed", "error": code}, arguments.diagnostics)
        print(code, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
