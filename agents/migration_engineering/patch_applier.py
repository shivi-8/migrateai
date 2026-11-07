"""Patch Applier for Agent 3.

Safely applies code transformations to an isolated migration workspace,
computes file-level unified diffs, and preserves original files.
"""

from __future__ import annotations

import difflib
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .models import FileChange


class PatchApplier:
    def __init__(self, workspace_base_dir: Optional[Path] = None):
        self.workspace_base = workspace_base_dir or (
            Path(__file__).resolve().parents[2] / "migration_workspaces"
        )
        self.workspace_base.mkdir(parents=True, exist_ok=True)

    def prepare_workspace(self, source_dir: Path, migration_id: str) -> Path:
        """Create a separate working copy for this migration job."""
        workspace = self.workspace_base / migration_id
        if workspace.exists():
            shutil.rmtree(workspace)
        shutil.copytree(
            source_dir,
            workspace,
            ignore=shutil.ignore_patterns(".git", "node_modules", ".venv", "__pycache__", "dist"),
        )
        return workspace

    def compute_diff(self, original: str, modified: str, file_path: str) -> str:
        """Generate unified diff string between original and modified text."""
        orig_lines = original.splitlines(keepends=True)
        mod_lines = modified.splitlines(keepends=True)
        diff = difflib.unified_diff(
            orig_lines,
            mod_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )
        return "".join(diff)

    def apply_file_change(
        self,
        workspace_dir: Path,
        rel_path: str,
        new_content: str,
        original_content: Optional[str] = None,
        dry_run: bool = True,
        change_descriptions: Optional[List[str]] = None,
        review_required: bool = False,
    ) -> FileChange:
        """Apply or simulate applying a file change."""
        target_path = workspace_dir / rel_path
        status = "modified"
        if not target_path.exists():
            status = "created"

        orig_text = ""
        if original_content is not None:
            orig_text = original_content
        elif target_path.is_file():
            try:
                orig_text = target_path.read_text(encoding="utf-8")
            except Exception:
                orig_text = ""

        diff = self.compute_diff(orig_text, new_content, rel_path) if orig_text != new_content else None

        if not dry_run:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(new_content, encoding="utf-8")

        return FileChange(
            file=rel_path,
            status=status,
            changes=change_descriptions or [],
            review_required=review_required,
            diff=diff,
            reason="Prisma migration transformation" if status == "modified" else "Generated target file",
        )
