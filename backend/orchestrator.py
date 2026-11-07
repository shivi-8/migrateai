"""Coordinates the pipeline: fetch repository -> Node.js analyzer (scanner + Agent 1) -> JSON.

Security notes
  * Repository URLs and branches are validated before use (see schemas.py).
  * git and node are started with argument lists, never through a shell.
  * Repository code is only read and parsed, never executed, installed or built.
  * Clones are shallow, time-limited and deleted after analysis.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from schemas import (
    AnalysisResponse,
    AnalyzeRequest,
    EngineeringResult,
    MigrationPlan,
    parse_github_url,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYZER_DIR = Path(os.environ.get("MIGRATEAI_ANALYZER_DIR", REPO_ROOT / "analyzer"))
SAMPLE_DIR = REPO_ROOT / "tests" / "fixtures" / "sample-app"
MIGRATION_PLANNER_DIR = REPO_ROOT / "migration_planner"
AGENTS_DIR = REPO_ROOT / "agents"
SNAPSHOTS_DIR = REPO_ROOT / "migration_workspaces" / "snapshots"
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

if str(MIGRATION_PLANNER_DIR) not in sys.path:
    sys.path.insert(0, str(MIGRATION_PLANNER_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from migration.planner import create_migration_plan
except ImportError:
    from migration_planner.migration.planner import create_migration_plan

from agents.migration_engineering import MigrationEngineeringAgent

CLONE_TIMEOUT_S = int(os.environ.get("MIGRATEAI_CLONE_TIMEOUT", "120"))
ANALYZE_TIMEOUT_S = int(os.environ.get("MIGRATEAI_ANALYZE_TIMEOUT", "120"))
MAX_ANALYZER_OUTPUT = 50 * 1024 * 1024
MAX_STORED_ANALYSES = 50
MAX_CONCURRENT_JOBS = 2

_jobs = threading.BoundedSemaphore(MAX_CONCURRENT_JOBS)
_store: "OrderedDict[str, AnalysisResponse]" = OrderedDict()
_engineering_store: "OrderedDict[str, EngineeringResult]" = OrderedDict()
_store_lock = threading.Lock()
_engineering_agent = MigrationEngineeringAgent()


class OrchestratorError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Step 1 — fetch the repository
# ---------------------------------------------------------------------------


def clone_repo(owner: str, repo: str, branch: Optional[str], dest: Path) -> None:
    url = f"https://github.com/{owner}/{repo}.git"
    cmd = [
        "git",
        "-c", "protocol.allow=never",
        "-c", "protocol.https.allow=always",
        "-c", "core.symlinks=false",
        "clone",
        "--depth", "1",
        "--single-branch",
        "--no-tags",
    ]
    if branch:
        cmd += ["--branch", branch]
    cmd += ["--", url, str(dest)]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}  # never block waiting for credentials

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=CLONE_TIMEOUT_S, env=env)
    except FileNotFoundError:
        raise OrchestratorError("git is not installed on the server.", 500)
    except subprocess.TimeoutExpired:
        raise OrchestratorError(f"Cloning timed out after {CLONE_TIMEOUT_S}s. The repository may be too large.", 504)

    if proc.returncode != 0:
        err = (proc.stderr or "").lower()
        if "remote branch" in err and "not found" in err:
            raise OrchestratorError(f"Branch '{branch}' was not found in {owner}/{repo}.", 404)
        if "not found" in err or "authentication" in err or "could not read username" in err:
            raise OrchestratorError(f"Repository {owner}/{repo} was not found, or it is private.", 404)
        raise OrchestratorError("Could not clone the repository.", 502)


# ---------------------------------------------------------------------------
# Steps 2-4 — scanner + Agent 1 (Node.js analyzer)
# ---------------------------------------------------------------------------


def run_analyzer(root: Path, scope: str = "relevant", generate_graph: bool = True) -> Dict[str, Any]:
    node = shutil.which("node")
    if not node:
        raise OrchestratorError("Node.js is required to run the analyzer but was not found.", 500)
    cli = ANALYZER_DIR / "dist" / "cli.js"
    if not cli.is_file():
        raise OrchestratorError("The analyzer is not built. Run `npm install && npm run build` in the analyzer folder.", 500)

    cmd = [node, str(cli), "--root", str(root), "--scope", scope]
    if not generate_graph:
        cmd.append("--no-graph")
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=ANALYZE_TIMEOUT_S, cwd=str(ANALYZER_DIR))
    except subprocess.TimeoutExpired:
        raise OrchestratorError(f"Analysis timed out after {ANALYZE_TIMEOUT_S}s.", 504)

    stderr = proc.stderr.decode("utf-8", "replace")
    if proc.returncode != 0:
        if "Cannot find module" in stderr:
            raise OrchestratorError("Analyzer dependencies are missing. Run `npm install` in the analyzer folder.", 500)
        raise OrchestratorError("The analyzer failed to process this repository.", 500)
    if len(proc.stdout) > MAX_ANALYZER_OUTPUT:
        raise OrchestratorError("The analysis result was too large to return.", 413)
    try:
        return json.loads(proc.stdout.decode("utf-8"))
    except ValueError:
        raise OrchestratorError("The analyzer returned invalid output.", 500)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def _build_response(
    payload: Dict[str, Any], *, source: str, repository_url: Optional[str], branch: Optional[str]
) -> AnalysisResponse:
    raw_findings = payload.get("findings", [])
    raw_plan = create_migration_plan(raw_findings)
    response = AnalysisResponse.model_validate(
        {
            **payload,  # camelCase keys straight from the analyzer
            "id": uuid.uuid4().hex[:12],
            "source": source,
            "repositoryUrl": repository_url,
            "branch": branch,
            "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "plan": raw_plan,
        }
    )
    with _store_lock:
        _store[response.id] = response
        while len(_store) > MAX_STORED_ANALYSES:
            _store.popitem(last=False)
    return response


def generate_migration_plan(analysis: AnalysisResponse) -> MigrationPlan:
    """Agent 2: Create a migration plan from the analysis findings."""
    raw_findings = [f.model_dump() for f in analysis.findings]
    plan_dict = create_migration_plan(raw_findings)
    return MigrationPlan.model_validate(plan_dict)


def analyze_repository(request: AnalyzeRequest) -> AnalysisResponse:
    owner, repo = parse_github_url(request.repository_url)
    if not _jobs.acquire(blocking=False):
        raise OrchestratorError("The server is busy analyzing other repositories. Try again shortly.", 429)
    try:
        with tempfile.TemporaryDirectory(prefix="migrateai-") as tmp:
            dest = Path(tmp) / "repo"
            clone_repo(owner, repo, request.branch, dest)
            payload = run_analyzer(dest, request.graph_scope, request.generate_graph)
        return _build_response(
            payload,
            source="github",
            repository_url=f"https://github.com/{owner}/{repo}",
            branch=request.branch,
        )
    finally:
        _jobs.release()


def analyze_sample(generate_graph: bool = True, scope: str = "relevant") -> AnalysisResponse:
    """Analyze the bundled sample Express + Mongoose app (works offline; used for demos and tests)."""
    if not SAMPLE_DIR.is_dir():
        raise OrchestratorError("The bundled sample app is missing.", 500)
    payload = run_analyzer(SAMPLE_DIR, scope, generate_graph)
    return _build_response(payload, source="sample", repository_url=None, branch=None)


def get_analysis(analysis_id: str) -> Optional[AnalysisResponse]:
    with _store_lock:
        return _store.get(analysis_id)


def run_migration_engineering(
    analysis_id: str,
    task_ids: Optional[List[int]] = None,
    dry_run: bool = True,
) -> EngineeringResult:
    """Agent 3: Run migration engineering on the analyzed repository."""
    analysis = get_analysis(analysis_id)
    if not analysis:
        raise OrchestratorError(f"Analysis '{analysis_id}' not found.", 404)

    if not analysis.plan:
        analysis.plan = generate_migration_plan(analysis)

    # Determine source directory
    if analysis.source == "sample":
        source_dir = SAMPLE_DIR
    else:
        snapshot = SNAPSHOTS_DIR / analysis_id
        if not snapshot.is_dir():
            if not analysis.repository_url:
                raise OrchestratorError(f"Repository source for '{analysis_id}' is unavailable.", 404)
            owner, repo = parse_github_url(analysis.repository_url)
            clone_repo(owner, repo, analysis.branch, snapshot)
        source_dir = snapshot

    result = _engineering_agent.run(
        repo_dir=source_dir,
        analysis_data=analysis.model_dump(by_alias=True),
        task_ids=task_ids,
        dry_run=dry_run,
    )

    with _store_lock:
        _engineering_store[result.migration_id] = result
        analysis.engineering = result

    return result


def get_migration(migration_id: str) -> Optional[EngineeringResult]:
    with _store_lock:
        return _engineering_store.get(migration_id)
