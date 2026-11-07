"""Context Builder for Agent 3.

Retrieves complete source files, models, schemas, and function context
to ground transformations in real code rather than isolated method names.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .models import FieldDefinition, FunctionContext, ModelSchema


class ContextBuilder:
    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def read_file(self, rel_path: str) -> Optional[str]:
        target = self.repo_root / rel_path
        if not target.is_file():
            return None
        try:
            return target.read_text(encoding="utf-8")
        except Exception:
            return None

    def extract_models(self, model_files: Optional[List[str]] = None) -> Dict[str, ModelSchema]:
        """Extract Mongoose model schemas from model files."""
        schemas: Dict[str, ModelSchema] = {}
        if not model_files:
            valid_exts = {".js", ".ts", ".mjs", ".cjs", ".jsx", ".tsx"}
            model_files = [
                str(p.relative_to(self.repo_root)).replace("\\", "/")
                for p in self.repo_root.rglob("*")
                if "models" in p.parts and p.is_file() and p.suffix in valid_exts
            ]

        for rel_path in model_files:
            code = self.read_file(rel_path)
            if not code:
                continue

            model_name = self._extract_model_name(code, rel_path)
            if not model_name:
                continue

            fields, has_timestamps = self._parse_schema_body(code)
            schemas[model_name] = ModelSchema(
                name=model_name,
                fields=fields,
                has_timestamps=has_timestamps,
            )

        return schemas

    def _extract_model_name(self, code: str, rel_path: str) -> Optional[str]:
        m = re.search(r"mongoose\.model\(\s*['\"](\w+)['\"]", code)
        if m:
            return m.group(1)
        stem = Path(rel_path).stem
        if stem and stem[0].isupper():
            return stem
        return None

    def _parse_schema_body(self, code: str) -> Tuple[Dict[str, FieldDefinition], bool]:
        fields: Dict[str, FieldDefinition] = {}
        has_timestamps = bool(re.search(r"timestamps\s*:\s*true", code))

        schema_match = re.search(r"new\s+(?:mongoose\.)?Schema\(\s*\{([\s\S]*?)\}\s*(?:,\s*\{([\s\S]*?)\})?\s*\)", code)
        if not schema_match:
            return fields, has_timestamps

        body = schema_match.group(1)

        prop_pattern = re.compile(
            r"(\w+)\s*:\s*(\[\s*\{[\s\S]*?\}\s*\]|\[[\s\S]*?\]|\{[\s\S]*?\}|\w+(?:\.\w+)*)"
        )

        for pm in prop_pattern.finditer(body):
            prop_name = pm.group(1)
            prop_def = pm.group(2).strip()

            is_list = prop_def.startswith("[") and prop_def.endswith("]")
            inner = prop_def[1:-1].strip() if is_list else prop_def

            field_type = "String"
            is_required = False
            is_unique = False
            relation_model = None

            if "ObjectId" in inner:
                field_type = "ObjectId"
            elif "String" in inner:
                field_type = "String"
            elif "Number" in inner:
                field_type = "Int"
            elif "Boolean" in inner:
                field_type = "Boolean"
            elif "Date" in inner:
                field_type = "DateTime"

            ref_match = re.search(r"ref\s*:\s*['\"](\w+)['\"]", inner)
            if ref_match:
                relation_model = ref_match.group(1)

            if "required" in inner and "true" in inner:
                is_required = True
            if "unique" in inner and "true" in inner:
                is_unique = True

            fields[prop_name] = FieldDefinition(
                name=prop_name,
                field_type=field_type,
                is_required=is_required,
                is_unique=is_unique,
                is_list=is_list,
                relation_model=relation_model,
            )

        return fields, has_timestamps

    def extract_functions(self, rel_path: str) -> List[FunctionContext]:
        """Extract functions from a source file."""
        code = self.read_file(rel_path)
        if not code:
            return []

        functions: List[FunctionContext] = []

        pattern = re.compile(
            r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\((.*?)\)\s*\{|"
            r"^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\((.*?)\)\s*=>\s*\{",
            re.MULTILINE
        )

        matches = list(pattern.finditer(code))
        for match in matches:
            fn_name = match.group(1) or match.group(3)
            start_pos = match.start()
            start_line = code[:start_pos].count("\n") + 1

            brace_count = 0
            open_found = False
            end_pos = len(code)
            for pos in range(start_pos, len(code)):
                char = code[pos]
                if char == "{":
                    brace_count += 1
                    open_found = True
                elif char == "}":
                    brace_count -= 1
                    if open_found and brace_count == 0:
                        end_pos = pos + 1
                        break

            fn_code = code[start_pos:end_pos]
            end_line = code[:end_pos].count("\n") + 1

            functions.append(
                FunctionContext(
                    file_path=rel_path,
                    function_name=fn_name,
                    source_code=fn_code,
                    line_start=start_line,
                    line_end=end_line,
                )
            )

        return functions
