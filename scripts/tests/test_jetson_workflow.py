import ast
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/network-camera.yml").read_text()
        match = re.search(r"(?ms)^  deploy-jetson:\n(.*?)(?=^  [a-z][a-z-]*:|\Z)", self.workflow)
        self.assertIsNotNone(match, "deployment job is required")
        self.job = match.group(1)

    def test_gates_environment_permissions_and_serialization_are_explicit(self):
        for required in (
            "needs: [linux-camera, dashboard, deployment-tests]", "environment: jetson-production",
            "github.repository == 'Arasaka-Academy/CyberVisual'", "github.ref == 'refs/heads/main'",
            "vars.JETSON_DEPLOY_ENABLED == 'true'", "github.event_name == 'push'", "github.event_name == 'workflow_dispatch'",
            "needs.linux-camera.result == 'success'", "needs.dashboard.result == 'success'", "needs.deployment-tests.result == 'success'",
            "contents: read", "id-token: write", "cancel-in-progress: false", "group: cybervisual-jetson-production",
        ):
            self.assertIn(required, self.job)
        self.assertNotIn("write-all", self.job)
        self.assertNotIn("pull_request_target", self.workflow)

    def test_oidc_inputs_and_all_actions_are_commit_pinned(self):
        self.assertIn("tailscale/github-action@064b10558093f38325e838ddea35486bdc6b1d5c", self.job)
        for required in ("oauth-client-id: ${{ vars.TS_OIDC_CLIENT_ID }}", "audience: ${{ vars.TS_OIDC_AUDIENCE }}",
                         "tags: tag:cybervisual-ci", "version: '1.104.5'"):
            self.assertIn(required, self.job)
        for forbidden in ("oauth-secret", "authkey", "ssh-private-key", "secrets."):
            self.assertNotIn(forbidden, self.job)
        for action in re.findall(r"uses:\s*(\S+)", self.workflow):
            self.assertRegex(action, r"^[\w-]+/[\w-]+@[0-9a-f]{40}$")

    def test_artifact_gate_and_diagnostics_do_not_bypass_existing_checks(self):
        self.assertIn("python3 scripts/jetson_release.py gate", self.job)
        self.assertLess(self.job.index("scripts/jetson_release.py gate"), self.job.index("tailscale/github-action@"))
        self.assertIn("steps.gate.outputs.latest == 'true'", self.job)
        self.assertIn("CI_RESULTS: ${{ toJSON(needs) }}", self.job)
        self.assertIn("retention-days: 14", self.job)
        self.assertIn("status.json", self.job)
        for required in ("npm test", "npm run test:e2e", "git diff --exit-code -- dist", "RUN_CAMERA_INTEROP=1",
                         "python3 -m unittest discover -s scripts/tests -v", "scripts/jetson_release.py package"):
            self.assertIn(required, self.workflow)

    def test_target_scripts_are_python36_compatible(self):
        for name in ("jetson_deploy.py", "jetson_bootstrap.py", "jetson_release.py"):
            ast.parse((ROOT / "scripts" / name).read_text(), feature_version=(3, 6))

    def test_sudo_wrapper_cannot_invoke_internal_worker_or_override_paths(self):
        wrapper = (ROOT / "scripts/deploy_jetson.sh").read_text()
        self.assertIn("publish|status|rollback)", wrapper)
        self.assertNotIn("_apply)", wrapper)
        self.assertIn("/usr/bin/env -i", wrapper)
        self.assertIn("/usr/local/lib/cybervisual-deploy/jetson_deploy.py", wrapper)

    def test_identity_templates_restrict_all_claims_and_only_deployment_ssh(self):
        identity = json.loads((ROOT / "deploy/jetson/tailscale-oidc.json").read_text())
        self.assertEqual(identity["scopes"], ["auth_keys"])
        self.assertEqual(identity["tags"], ["tag:cybervisual-ci"])
        self.assertEqual(identity["subject"], "repo:Arasaka-Academy/CyberVisual:environment:jetson-production")
        self.assertEqual(identity["custom_claim_rules"], {
            "repository": "Arasaka-Academy/CyberVisual", "ref": "refs/heads/main", "environment": "jetson-production",
            "workflow_ref": "Arasaka-Academy/CyberVisual/.github/workflows/network-camera.yml@refs/heads/main",
        })
        policy = json.loads((ROOT / "deploy/jetson/tailscale-policy-fragment.json").read_text())
        self.assertEqual(policy["grants"], [{"src": ["tag:cybervisual-ci"], "dst": ["tag:cybervisual-jetson"], "ip": ["tcp:22"]}])
        self.assertEqual(policy["ssh"], [{"action": "accept", "src": ["tag:cybervisual-ci"], "dst": ["tag:cybervisual-jetson"], "users": ["cybervisual-deploy"]}])


if __name__ == "__main__":
    unittest.main()
