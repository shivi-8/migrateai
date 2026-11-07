"""Request/response contract shared by the API, the analyzer and the dashboard.

Requests use snake_case (as in the project plan). Responses are serialized in camelCase so they
match the analyzer's JSON exactly and the frontend can use them as-is.
"""

from __future__ import annotations

import re
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel

# ---------------------------------------------------------------------------
# Input validation — every repository is untrusted input.
# ---------------------------------------------------------------------------

_GITHUB_URL = re.compile(
    r"^https://github\.com/"
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/"
    r"(?P<repo>[A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$"
)
_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")


def parse_github_url(url: str) -> tuple[str, str]:
    """Return (owner, repo) for a plain https://github.com/owner/repo URL, else raise ValueError."""
    match = _GITHUB_URL.match(url.strip())
    if not match:
        raise ValueError("Enter a GitHub repository URL like https://github.com/owner/repo")
    owner, repo = match.group("owner"), match.group("repo")
    if repo in {".", ".."}:
        raise ValueError("Invalid repository name")
    return owner, repo


def validate_branch(branch: str) -> str:
    branch = branch.strip()
    if (
        not _BRANCH.match(branch)
        or ".." in branch
        or "//" in branch
        or branch.endswith(("/", ".lock", "."))
    ):
        raise ValueError("Invalid branch name")
    return branch


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_url: str
    branch: Optional[str] = None
    generate_graph: bool = True
    graph_scope: Literal["relevant", "all"] = "relevant"

    @field_validator("repository_url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        parse_github_url(value)
        return value.strip()

    @field_validator("branch")
    @classmethod
    def _check_branch(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        return validate_branch(value)


# ---------------------------------------------------------------------------
# Response models (mirror analyzer/src/types.ts)
# ---------------------------------------------------------------------------

Category = Literal[
    "Dependencies", "Connection", "Schema", "Model", "Queries", "Relationships", "Database operations"
]
Confidence = Literal["high", "medium", "low"]
NodeKind = Literal["entry", "route", "controller", "service", "model", "database", "file"]
EdgeType = Literal["imports", "registers_route", "calls_service", "uses_model", "connects_db"]
Impact = Literal["direct", "indirect", "none"]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Finding(CamelModel):
    file: str
    line: int
    column: int
    category: Category
    pattern: str
    evidence: str
    confidence: Confidence
    detail: Optional[str] = None


class GraphNode(CamelModel):
    id: str
    label: str
    path: str
    kind: NodeKind
    mongo: bool
    impact: Impact
    categories: List[Category]
    finding_count: int
    models: List[str]


class GraphEdge(CamelModel):
    id: str
    source: str
    target: str
    type: EdgeType
    label: Optional[str] = None


class Graph(CamelModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    impact: Dict[str, List[str]]


class AffectedFile(CamelModel):
    file: str
    kind: NodeKind
    finding_count: int
    categories: List[Category]


class Summary(CamelModel):
    files_scanned: int
    files_with_findings: int
    total_findings: int
    by_category: Dict[str, int]
    by_confidence: Dict[str, int]
    model_count: int
    models: List[str]
    driver: Literal["mongoose", "mongodb", "both", "none"]
    parse_failures: int
    truncated: bool
    node_count: int
    edge_count: int
    duration_ms: int


# ---------------------------------------------------------------------------
# Agent 2 — Migration Planner response models
# ---------------------------------------------------------------------------


class MigrationTask(CamelModel):
    id: int
    file: str
    line: Optional[int] = None
    model: Optional[str] = None
    source_operation: Optional[str] = None
    target_operation: Optional[str] = None
    action: str
    reason: str
    priority: Literal["high", "medium", "low"]
    status: str = "pending"
    manual_review: bool = True


class MigrationBlocker(CamelModel):
    file: str
    line: Optional[int] = None
    pattern: str
    keyword: str
    severity: Literal["high", "medium", "low"]
    reason: str


class MigrationWarning(CamelModel):
    file: Optional[str] = None
    line: Optional[int] = None
    operation: Optional[str] = None
    finding_index: Optional[int] = None
    message: str


class MigrationPlanSummary(CamelModel):
    findings_received: int
    findings_processed: int
    tasks_created: int
    blockers_found: int
    warnings_count: int


class MigrationPlan(CamelModel):
    source: str = "MongoDB/Mongoose"
    target: str = "PostgreSQL/Prisma"
    summary: MigrationPlanSummary
    blockers: List[MigrationBlocker] = []
    warnings: List[MigrationWarning] = []
    tasks: List[MigrationTask] = []


# ---------------------------------------------------------------------------
# Agent 3 — Migration Engineering models
# ---------------------------------------------------------------------------


class FileChange(CamelModel):
    file: str
    status: Literal["modified", "created", "skipped"]
    changes: List[str] = []
    review_required: bool = False
    diff: Optional[str] = None
    reason: Optional[str] = None


class EngineeringRequest(BaseModel):
    task_ids: Optional[List[int]] = None
    dry_run: bool = True
    require_approval: bool = True


class EngineeringResult(CamelModel):
    migration_id: str
    status: Literal["completed", "partial", "dry_run"]
    files_modified: int = 0
    files_created: int = 0
    files_skipped: int = 0
    files: List[FileChange] = []
    unresolved_tasks: List[int] = []
    diff_available: bool = False
    prisma_schema: Optional[str] = None
    workspace_dir: Optional[str] = None


class AnalysisResponse(CamelModel):
    id: str
    source: Literal["github", "sample"]
    repository_url: Optional[str] = None
    branch: Optional[str] = None
    created_at: str
    summary: Summary
    findings: List[Finding]
    affected_files: List[AffectedFile]
    graph: Optional[Graph] = None
    warnings: List[str]
    plan: Optional[MigrationPlan] = None
    engineering: Optional[EngineeringResult] = None
