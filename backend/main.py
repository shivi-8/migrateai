"""MigrateAI API. Run from this folder: uvicorn main:app --reload --port 8001"""

from __future__ import annotations

import os
from typing import Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import orchestrator
from schemas import (
    AnalysisResponse,
    AnalyzeRequest,
    EngineeringRequest,
    EngineeringResult,
    Graph,
    MigrationPlan,
)

app = FastAPI(title="MigrateAI API", version="0.2.0")

_origins = [o.strip() for o in os.environ.get("MIGRATEAI_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["GET", "POST"], allow_headers=["*"])


def _fail(err: orchestrator.OrchestratorError) -> HTTPException:
    return HTTPException(status_code=err.status_code, detail=err.message)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalysisResponse)
def analyze(request: AnalyzeRequest) -> AnalysisResponse:
    """Fetch a GitHub repository, scan it for MongoDB/Mongoose code and build the dependency graph."""
    try:
        return orchestrator.analyze_repository(request)
    except orchestrator.OrchestratorError as err:
        raise _fail(err)


@app.post("/analyze/sample", response_model=AnalysisResponse)
def analyze_sample(scope: Literal["relevant", "all"] = "relevant") -> AnalysisResponse:
    """Analyze the bundled sample app. Needs no network access."""
    try:
        return orchestrator.analyze_sample(scope=scope)
    except orchestrator.OrchestratorError as err:
        raise _fail(err)


@app.get("/analysis/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: str) -> AnalysisResponse:
    found = orchestrator.get_analysis(analysis_id)
    if not found:
        raise HTTPException(status_code=404, detail="Analysis not found (results are kept in memory only).")
    return found


@app.get("/analysis/{analysis_id}/graph", response_model=Graph)
def get_graph(analysis_id: str) -> Graph:
    found = orchestrator.get_analysis(analysis_id)
    if not found:
        raise HTTPException(status_code=404, detail="Analysis not found (results are kept in memory only).")
    if found.graph is None:
        raise HTTPException(status_code=404, detail="This analysis was run without a dependency graph.")
    return found.graph


# ---------------------------------------------------------------------------
# Agent 2 (Migration Planner)
# ---------------------------------------------------------------------------


@app.post("/analysis/{analysis_id}/migrate", response_model=MigrationPlan)
def migrate(analysis_id: str) -> MigrationPlan:
    """Run Agent 2 (Migration Planner) to create a migration plan for this analysis."""
    found = orchestrator.get_analysis(analysis_id)
    if not found:
        raise HTTPException(status_code=404, detail="Analysis not found (results are kept in memory only).")
    if not found.plan:
        found.plan = orchestrator.generate_migration_plan(found)
    return found.plan


@app.get("/analysis/{analysis_id}/plan", response_model=MigrationPlan)
def get_plan(analysis_id: str) -> MigrationPlan:
    """Retrieve the Agent 2 migration plan for this analysis."""
    found = orchestrator.get_analysis(analysis_id)
    if not found:
        raise HTTPException(status_code=404, detail="Analysis not found (results are kept in memory only).")
    if not found.plan:
        found.plan = orchestrator.generate_migration_plan(found)
    return found.plan


# ---------------------------------------------------------------------------
# Agent 3 (Migration Engineering)
# ---------------------------------------------------------------------------


@app.post("/analysis/{analysis_id}/engineer", response_model=EngineeringResult)
def engineer(
    analysis_id: str,
    request: Optional[EngineeringRequest] = None,
) -> EngineeringResult:
    """Run Agent 3 (Migration Engineering) to generate Prisma schema and code changes."""
    task_ids = request.task_ids if request else None
    dry_run = request.dry_run if request else True
    try:
        return orchestrator.run_migration_engineering(
            analysis_id=analysis_id,
            task_ids=task_ids,
            dry_run=dry_run,
        )
    except orchestrator.OrchestratorError as err:
        raise _fail(err)


@app.get("/migration/{migration_id}", response_model=EngineeringResult)
def get_migration(migration_id: str) -> EngineeringResult:
    """Retrieve the migration engineering result by migration ID."""
    result = orchestrator.get_migration(migration_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Migration '{migration_id}' not found.")
    return result


@app.get("/migration/{migration_id}/diff")
def get_migration_diff(migration_id: str) -> Dict[str, Optional[str]]:
    """Retrieve file-level unified diffs for a migration."""
    result = orchestrator.get_migration(migration_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Migration '{migration_id}' not found.")
    return {f.file: f.diff for f in result.files if f.diff}


# ---------------------------------------------------------------------------
# Agent 4 (Validation)
# ---------------------------------------------------------------------------


@app.post("/analysis/{analysis_id}/validate")
def validate(analysis_id: str) -> None:
    raise HTTPException(status_code=501, detail="The validation stage is not implemented yet.")
