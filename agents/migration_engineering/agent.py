"""Agent 3 — Migration Engineering Agent.

Context-aware code transformation engine for MongoDB/Mongoose to PostgreSQL/Prisma.
Translates schemas, replaces database queries, handles relations, and writes
diffs to an isolated workspace.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .code_generator import CodeGenerator
from .context_builder import ContextBuilder
from .llm_client import LLMClient
from .models import EngineeringResult, FileChange, FunctionContext, ModelSchema
from .patch_applier import PatchApplier
from .schema_generator import SchemaGenerator
from .transformation_engine import TransformationEngine


class MigrationEngineeringAgent:
    def __init__(
        self,
        workspace_base_dir: Optional[Path] = None,
        llm_client: Optional[LLMClient] = None,
    ):
        self.patch_applier = PatchApplier(workspace_base_dir)
        self.code_generator = CodeGenerator()
        self.llm_client = llm_client or LLMClient()

    def run(
        self,
        repo_dir: Path,
        analysis_data: Dict[str, Any],
        task_ids: Optional[List[int]] = None,
        dry_run: bool = True,
    ) -> EngineeringResult:
        migration_id = uuid.uuid4().hex[:12]
        workspace = self.patch_applier.prepare_workspace(repo_dir, migration_id)
        context_builder = ContextBuilder(workspace)

        # 1. Extract models & generate Prisma schema
        model_schemas = context_builder.extract_models()
        schema_gen = SchemaGenerator(model_schemas)
        prisma_schema_content = schema_gen.generate()

        transform_engine = TransformationEngine(
            llm_client=self.llm_client, prisma_schema=prisma_schema_content
        )

        # 2. Filter migration tasks
        plan = analysis_data.get("plan") or {}
        tasks = plan.get("tasks", [])
        if task_ids is not None:
            selected_task_ids = set(task_ids)
            tasks = [t for t in tasks if t.get("id") in selected_task_ids]

        # Group tasks by file
        tasks_by_file: Dict[str, List[Dict[str, Any]]] = {}
        for t in tasks:
            f = t.get("file")
            if f and f != "Unknown file":
                tasks_by_file.setdefault(f, []).append(t)

        file_changes: List[FileChange] = []
        unresolved_tasks: List[int] = []

        # 3. Apply schema.prisma
        schema_fc = self.patch_applier.apply_file_change(
            workspace_dir=workspace,
            rel_path="prisma/schema.prisma",
            new_content=prisma_schema_content,
            dry_run=dry_run,
            change_descriptions=["Generated PostgreSQL Prisma schema from Mongoose models"],
        )
        file_changes.append(schema_fc)

        # 4. Generate src/config/prisma.js
        pkg_code = context_builder.read_file("package.json") or ""
        is_esm = '"type": "module"' in pkg_code

        prisma_client_code = self.code_generator.generate_prisma_client_module(is_esm=is_esm)
        client_fc = self.patch_applier.apply_file_change(
            workspace_dir=workspace,
            rel_path="src/config/prisma.js",
            new_content=prisma_client_code,
            dry_run=dry_run,
            change_descriptions=["Created PrismaClient database connection module"],
        )
        file_changes.append(client_fc)

        # 5. Transform service files
        for rel_file, file_tasks in tasks_by_file.items():
            orig_file_code = context_builder.read_file(rel_file)
            if not orig_file_code:
                continue

            functions = context_builder.extract_functions(rel_file)
            function_replacements: Dict[str, str] = {}
            file_change_notes: List[str] = []
            file_review_required = False
            associated_model = "User"

            # 5a. Process planned tasks
            for task in file_tasks:
                t_id = task.get("id")
                t_line = task.get("line")
                model_name = task.get("model") or "User"
                associated_model = model_name
                source_op = task.get("source_operation") or ""
                target_op = task.get("target_operation") or ""
                action = task.get("action", "")

                # Find matching function by line first, then by operation/keyword
                matching_fn: Optional[FunctionContext] = None
                if t_line:
                    for fn in functions:
                        if fn.line_start <= t_line <= fn.line_end:
                            matching_fn = fn
                            break

                if not matching_fn and source_op:
                    for fn in functions:
                        if f".{source_op}(" in fn.source_code:
                            matching_fn = fn
                            break

                if not matching_fn and "aggregate" in action.lower():
                    for fn in functions:
                        if "aggregate(" in fn.source_code:
                            matching_fn = fn
                            break

                if not matching_fn and "populate" in action.lower():
                    for fn in functions:
                        if "populate(" in fn.source_code:
                            matching_fn = fn
                            break

                if matching_fn:
                    current_code = function_replacements.get(matching_fn.source_code, matching_fn.source_code)
                    temp_fn = FunctionContext(
                        file_path=matching_fn.file_path,
                        function_name=matching_fn.function_name,
                        source_code=current_code,
                        model_name=model_name,
                        operation=source_op,
                    )
                    transformed_code, changes, review_needed = (
                        transform_engine.transform_function(
                            func=temp_fn,
                            model_name=model_name,
                            source_op=source_op or action,
                            target_op=target_op,
                        )
                    )
                    if transformed_code != matching_fn.source_code:
                        function_replacements[matching_fn.source_code] = transformed_code
                    file_change_notes.extend(changes)
                    if review_needed:
                        file_review_required = True
                        if t_id and t_id not in unresolved_tasks:
                            unresolved_tasks.append(t_id)
                else:
                    if t_id and t_id not in unresolved_tasks:
                        unresolved_tasks.append(t_id)

            # 5b. Pass remaining functions in the file through the engine if full migration (task_ids is None)
            if task_ids is None:
                for fn in functions:
                    if fn.source_code not in function_replacements:
                        transformed_code, changes, review_needed = (
                            transform_engine.transform_function(
                                func=fn,
                                model_name=associated_model,
                                source_op="",
                                target_op="",
                            )
                        )
                        if transformed_code != fn.source_code:
                            function_replacements[fn.source_code] = transformed_code
                            file_change_notes.extend(changes)
                        if review_needed:
                            file_review_required = True

            if function_replacements or file_change_notes or file_review_required:
                updated_code, import_changes = self.code_generator.update_service_file(
                    code=orig_file_code,
                    function_replacements=function_replacements,
                    model_name=associated_model,
                )
                file_change_notes.extend(import_changes)

                fc = self.patch_applier.apply_file_change(
                    workspace_dir=workspace,
                    rel_path=rel_file,
                    new_content=updated_code,
                    original_content=orig_file_code,
                    dry_run=dry_run,
                    change_descriptions=file_change_notes,
                    review_required=file_review_required,
                )
                file_changes.append(fc)

        # 6. Update package.json
        if pkg_code:
            updated_pkg, pkg_changes = self.code_generator.update_package_json(pkg_code)
            if pkg_changes:
                pkg_fc = self.patch_applier.apply_file_change(
                    workspace_dir=workspace,
                    rel_path="package.json",
                    new_content=updated_pkg,
                    original_content=pkg_code,
                    dry_run=dry_run,
                    change_descriptions=pkg_changes,
                )
                file_changes.append(pkg_fc)

        created_count = sum(1 for f in file_changes if f.status == "created")
        modified_count = sum(1 for f in file_changes if f.status == "modified")
        skipped_count = len(unresolved_tasks)

        status_str = "dry_run" if dry_run else ("completed" if not unresolved_tasks else "partial")

        return EngineeringResult(
            migration_id=migration_id,
            status=status_str,
            files_modified=modified_count,
            files_created=created_count,
            files_skipped=skipped_count,
            files=file_changes,
            unresolved_tasks=unresolved_tasks,
            diff_available=any(f.diff is not None for f in file_changes),
            prisma_schema=prisma_schema_content,
            workspace_dir=str(workspace) if not dry_run else None,
        )
