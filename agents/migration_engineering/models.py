"""Data models for Agent 3 (Migration Engineering)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FieldDefinition(BaseModel):
    name: str
    field_type: str  # String, Int, Boolean, DateTime, etc.
    is_required: bool = False
    is_unique: bool = False
    is_list: bool = False
    default: Optional[str] = None
    relation_model: Optional[str] = None
    foreign_key: Optional[str] = None


class ModelSchema(BaseModel):
    name: str
    fields: Dict[str, FieldDefinition] = Field(default_factory=dict)
    has_timestamps: bool = False


class FunctionContext(BaseModel):
    file_path: str
    function_name: str
    source_code: str
    model_name: Optional[str] = None
    operation: Optional[str] = None
    line_start: int = 1
    line_end: int = 1


class FileChange(CamelModel):
    file: str
    status: Literal["modified", "created", "skipped"]
    changes: List[str] = Field(default_factory=list)
    review_required: bool = False
    diff: Optional[str] = None
    reason: Optional[str] = None


class EngineeringRequest(BaseModel):
    analysis_id: str
    task_ids: Optional[List[int]] = None
    dry_run: bool = True
    require_approval: bool = True


class EngineeringResult(CamelModel):
    migration_id: str
    status: Literal["completed", "partial", "dry_run"]
    files_modified: int = 0
    files_created: int = 0
    files_skipped: int = 0
    files: List[FileChange] = Field(default_factory=list)
    unresolved_tasks: List[int] = Field(default_factory=list)
    diff_available: bool = False
    prisma_schema: Optional[str] = None
    workspace_dir: Optional[str] = None
