"""Backend tests. Run with:  python -m unittest discover -s tests -v   (or: pytest tests)

The API-level tests need fastapi + httpx and are skipped if those are not installed.
"""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import orchestrator  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from schemas import AnalyzeRequest, parse_github_url, validate_branch  # noqa: E402

HAS_FASTAPI = bool(importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx"))
ANALYZER_BUILT = (ROOT / "analyzer" / "dist" / "cli.js").is_file()


class InputValidation(unittest.TestCase):
    def test_accepts_plain_github_urls(self):
        self.assertEqual(parse_github_url("https://github.com/owner/example-node-app"), ("owner", "example-node-app"))
        self.assertEqual(parse_github_url("https://github.com/owner/repo.git"), ("owner", "repo"))
        self.assertEqual(parse_github_url("https://github.com/owner/repo/"), ("owner", "repo"))
        self.assertEqual(parse_github_url("https://github.com/o-w/my.repo_1"), ("o-w", "my.repo_1"))

    def test_rejects_everything_else(self):
        bad = [
            "http://github.com/owner/repo",
            "git@github.com:owner/repo.git",
            "file:///etc/passwd",
            "https://gitlab.com/owner/repo",
            "https://github.com.evil.com/owner/repo",
            "https://evil.com/https://github.com/owner/repo",
            "https://github.com/owner/repo; rm -rf /",
            "https://github.com/owner/repo extra",
            "https://github.com/owner/../repo",
            "https://github.com/owner/repo/tree/main",
            "https://user:pass@github.com/owner/repo",
            "https://github.com/owner",
            "https://github.com/-owner/repo",
            "ext::sh -c 'touch /tmp/x'",
            "",
        ]
        for url in bad:
            with self.subTest(url=url), self.assertRaises(ValueError):
                parse_github_url(url)

    def test_branch_validation(self):
        for ok in ["main", "feature/login", "release-1.2.3", "v2"]:
            self.assertEqual(validate_branch(ok), ok)
        for bad in ["--upload-pack=touch /tmp/x", "-b", "a b", "../x", "a//b", "x;y", "feat/", "a.lock", "$(id)", ""]:
            with self.subTest(branch=bad), self.assertRaises(ValueError):
                validate_branch(bad)

    def test_request_model(self):
        req = AnalyzeRequest(repository_url="https://github.com/owner/example-node-app", branch="main", generate_graph=True)
        self.assertEqual(req.graph_scope, "relevant")
        self.assertIsNone(AnalyzeRequest(repository_url="https://github.com/o/r", branch="  ").branch)
        with self.assertRaises(ValidationError):
            AnalyzeRequest(repository_url="https://github.com/o/r", branch="--exec=x")
        with self.assertRaises(ValidationError):
            AnalyzeRequest(repository_url="https://example.com/o/r")
        with self.assertRaises(ValidationError):
            AnalyzeRequest(repository_url="https://github.com/o/r", unexpected=1)


class CloneCommand(unittest.TestCase):
    def _run(self, returncode=0, stderr="", branch="main"):
        completed = subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)
        with mock.patch("orchestrator.subprocess.run", return_value=completed) as run:
            try:
                orchestrator.clone_repo("owner", "repo", branch, Path("/tmp/dest"))
            finally:
                self.run_mock = run
        return self.run_mock

    def test_uses_argument_list_without_shell_and_separates_url(self):
        run = self._run()
        cmd = run.call_args.args[0]
        self.assertIsInstance(cmd, list)
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertEqual(cmd[cmd.index("--") + 1], "https://github.com/owner/repo.git")
        self.assertIn("--depth", cmd)
        self.assertEqual(cmd[cmd.index("--branch") + 1], "main")
        self.assertEqual(run.call_args.kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")
        self.assertIn("timeout", run.call_args.kwargs)

    def test_error_mapping(self):
        with self.assertRaises(orchestrator.OrchestratorError) as ctx:
            self._run(128, "fatal: Remote branch nope not found in upstream origin", "nope")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("Branch", ctx.exception.message)
        with self.assertRaises(orchestrator.OrchestratorError) as ctx:
            self._run(128, "remote: Repository not found.", None)
        self.assertEqual(ctx.exception.status_code, 404)
        with self.assertRaises(orchestrator.OrchestratorError) as ctx:
            self._run(1, "something odd", None)
        self.assertEqual(ctx.exception.status_code, 502)

    def test_timeout_and_missing_git(self):
        with mock.patch("orchestrator.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 1)):
            with self.assertRaises(orchestrator.OrchestratorError) as ctx:
                orchestrator.clone_repo("o", "r", None, Path("/tmp/x"))
            self.assertEqual(ctx.exception.status_code, 504)
        with mock.patch("orchestrator.subprocess.run", side_effect=FileNotFoundError()):
            with self.assertRaises(orchestrator.OrchestratorError) as ctx:
                orchestrator.clone_repo("o", "r", None, Path("/tmp/x"))
            self.assertEqual(ctx.exception.status_code, 500)

    def test_analyze_repository_cleans_up_and_wires_pipeline(self):
        seen = {}

        def fake_clone(owner, repo, branch, dest):
            dest.mkdir(parents=True)
            seen["dest"] = dest

        with mock.patch("orchestrator.clone_repo", side_effect=fake_clone), mock.patch(
            "orchestrator.run_analyzer", return_value=_empty_payload()
        ) as analyzer:
            req = AnalyzeRequest(repository_url="https://github.com/owner/repo", branch="dev", graph_scope="all")
            result = orchestrator.analyze_repository(req)
        self.assertFalse(seen["dest"].exists(), "temporary clone must be deleted")
        self.assertEqual(analyzer.call_args.args[1:], ("all", True))
        self.assertEqual(result.repository_url, "https://github.com/owner/repo")
        self.assertEqual(result.branch, "dev")
        self.assertIs(orchestrator.get_analysis(result.id), result)
        self.assertIsNotNone(result.plan)

    def test_migration_plan_generated(self):
        payload = _empty_payload()
        payload["findings"] = [
            {"file": "src/services/userService.js", "line": 8, "column": 5, "category": "Queries", "pattern": "User.findById()", "evidence": "User.findById()", "confidence": "high", "detail": "User"},
            {"file": "src/services/postService.js", "line": 9, "column": 5, "category": "Database operations", "pattern": "Post.aggregate()", "evidence": "Post.aggregate()", "confidence": "high", "detail": "Post"},
        ]
        res = orchestrator._build_response(payload, source="sample", repository_url=None, branch=None)
        self.assertIsNotNone(res.plan)
        self.assertEqual(res.plan.source, "MongoDB/Mongoose")
        self.assertEqual(res.plan.target, "PostgreSQL/Prisma")
        self.assertEqual(res.plan.summary.tasks_created, 2)
        self.assertEqual(res.plan.summary.blockers_found, 1)
        plan = orchestrator.generate_migration_plan(res)
        self.assertEqual(plan.summary.tasks_created, 2)


@unittest.skipUnless(ANALYZER_BUILT, "analyzer is not built (cd analyzer && npm install && npm run build)")
class RealAnalyzer(unittest.TestCase):
    def test_sample_app_end_to_end(self):
        result = orchestrator.analyze_sample()
        self.assertEqual(result.source, "sample")
        self.assertEqual(result.summary.models, ["Post", "User"])
        self.assertGreater(result.summary.total_findings, 15)
        edges = {(e.source, e.target): e.type for e in result.graph.edges}
        self.assertEqual(edges[("src/server.js", "src/routes/userRoutes.js")], "registers_route")
        self.assertEqual(edges[("src/services/userService.js", "src/models/User.js")], "uses_model")
        dumped = result.model_dump(by_alias=True)
        self.assertIn("affectedFiles", dumped)
        self.assertIn("findingCount", dumped["graph"]["nodes"][0])

    def test_without_graph(self):
        result = orchestrator.analyze_sample(generate_graph=False)
        self.assertIsNone(result.graph)
        self.assertGreater(result.summary.total_findings, 0)

    def test_empty_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = orchestrator.run_analyzer(Path(tmp))
        self.assertEqual(payload["summary"]["totalFindings"], 0)
        self.assertEqual(payload["summary"]["driver"], "none")

    def test_missing_build_gives_actionable_error(self):
        with mock.patch.object(orchestrator, "ANALYZER_DIR", Path(tempfile.gettempdir()) / "nope"):
            with self.assertRaises(orchestrator.OrchestratorError) as ctx:
                orchestrator.run_analyzer(ROOT)
        self.assertIn("npm install", ctx.exception.message)


@unittest.skipUnless(HAS_FASTAPI and ANALYZER_BUILT, "needs fastapi, httpx and a built analyzer")
class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from main import app

        cls.client = TestClient(app)

    def test_health(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})

    def test_sample_then_fetch(self):
        r = self.client.post("/analyze/sample")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        g = self.client.get(f"/analysis/{body['id']}/graph")
        self.assertEqual(g.status_code, 200)
        self.assertEqual(len(g.json()["nodes"]), body["summary"]["nodeCount"])
        self.assertEqual(self.client.get(f"/analysis/{body['id']}").json()["id"], body["id"])
        # Agent 2 migration plan
        self.assertIn("plan", body)
        self.assertEqual(body["plan"]["source"], "MongoDB/Mongoose")
        self.assertEqual(body["plan"]["target"], "PostgreSQL/Prisma")
        m = self.client.post(f"/analysis/{body['id']}/migrate")
        self.assertEqual(m.status_code, 200)
        self.assertEqual(m.json()["source"], "MongoDB/Mongoose")
        p = self.client.get(f"/analysis/{body['id']}/plan")
        self.assertEqual(p.status_code, 200)

    def test_engineering_endpoints(self):
        r = self.client.post('/analyze/sample')
        analysis_id = r.json()['id']
        eng = self.client.post(f'/analysis/{analysis_id}/engineer', json={'dry_run': True})
        self.assertEqual(eng.status_code, 200)
        data = eng.json()
        self.assertEqual(data['status'], 'dry_run')
        self.assertTrue(data['diffAvailable'])
        self.assertGreater(data['filesCreated'], 0)
        mig_id = data['migrationId']
        fetched = self.client.get(f'/migration/{mig_id}')
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()['migrationId'], mig_id)
        diff_res = self.client.get(f'/migration/{mig_id}/diff')
        self.assertEqual(diff_res.status_code, 200)
        self.assertIsInstance(diff_res.json(), dict)

    def test_validation_and_errors(self):
        self.assertEqual(self.client.post("/analyze", json={"repository_url": "https://evil.com/x/y"}).status_code, 422)
        self.assertEqual(self.client.get("/analysis/missing").status_code, 404)
        self.assertEqual(self.client.post("/analysis/missing/migrate").status_code, 404)
        self.assertEqual(self.client.post("/analysis/x/validate").status_code, 501)


def _empty_payload():
    return {
        "summary": {
            "filesScanned": 0, "filesWithFindings": 0, "totalFindings": 0, "byCategory": {}, "byConfidence": {},
            "modelCount": 0, "models": [], "driver": "none", "parseFailures": 0, "truncated": False,
            "nodeCount": 0, "edgeCount": 0, "durationMs": 1,
        },
        "findings": [],
        "affectedFiles": [],
        "graph": {"nodes": [], "edges": [], "impact": {}},
        "warnings": [],
    }


if __name__ == "__main__":
    unittest.main()
