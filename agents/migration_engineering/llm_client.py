"""LLM Client for Agent 3 (Ollama / Local or Cloud Coding LLM).

Provides structured AI code transformations with deterministic fallback.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


class LLMClient:
    def __init__(self, host: Optional[str] = None, model: Optional[str] = None):
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = model or os.environ.get("MIGRATEAI_LLM_MODEL", "qwen2.5-coder:7b")
        prompt_path = Path(__file__).parent / "prompts" / "migration_prompt.txt"
        self.prompt_template = (
            prompt_path.read_text(encoding="utf-8") if prompt_path.is_file() else ""
        )

    def is_available(self, timeout_s: float = 1.0) -> bool:
        """Check if the Ollama endpoint is reachable."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return resp.status == 200
        except Exception:
            return False

    def transform_code(
        self,
        source_code: str,
        source_operation: str,
        target_operation: str,
        model_name: str,
        file_path: str,
        prisma_schema: str = "",
        timeout_s: float = 15.0,
    ) -> Optional[Dict[str, Any]]:
        """Ask LLM to perform contextual transformation."""
        if not self.is_available():
            return None

        prompt = self.prompt_template.format(
            source_code=source_code,
            source_operation=source_operation,
            target_operation=target_operation,
            model_name=model_name,
            file_path=file_path,
            prisma_schema=prisma_schema,
        )

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.host}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                response_text = result.get("response", "")
                return json.loads(response_text)
        except Exception:
            return None
