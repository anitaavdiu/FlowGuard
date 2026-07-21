"""Anthropic API client for cognitive-load diagnosis.

Called only when the EWMA score crosses the OVERLOADED threshold.
Returns a structured DiagnosisResult or None if the API key is absent
or the request fails — the caller handles the None case gracefully.
"""

import json
import os
from typing import Optional

import anthropic

from models import DiagnosisResult

_client: Optional[anthropic.AsyncAnthropic] = None

SYSTEM_PROMPT = """You are FlowGuard Core, an embedded cognitive-load intelligence engine for VS Code.

Given developer telemetry (deletion rate, file switches, error count, active file, \
error diagnostics, semantic signals, and a code snippet), output a JSON diagnosis \
of the overload trigger.

Rules:
- Identify the ONE most likely cause from the available data
- patch: a short human-readable description of the fix
- patch_code: syntactically valid code to insert at the cursor; empty string when \
  a direct single-insertion fix does not apply — match the language of the active file
- confidence (0.0–1.0) reflects how strongly the telemetry supports your diagnosis
- If no code snippet is available, diagnose from behavioral signals alone"""


def _get_client() -> Optional[anthropic.AsyncAnthropic]:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            _client = anthropic.AsyncAnthropic(api_key=api_key)
    return _client


async def get_diagnosis(
    score: float,
    backspace_count: int,
    file_switch_count: int,
    error_count: int,
    active_file: Optional[str],
    semantic_trigger: Optional[str],
    diagnostics: Optional[list[str]],
    snippet: Optional[str],
) -> Optional[DiagnosisResult]:
    client = _get_client()
    if client is None:
        return None

    diag_lines = ", ".join(diagnostics) if diagnostics else "none"
    lines = [
        f"Telemetry snapshot (score {score:.1f}/100 — OVERLOADED):",
        f"- Deletions last 60s: {backspace_count}",
        f"- File switches last 60s: {file_switch_count}",
        f"- Workspace errors: {error_count}",
        f"- Active file: {active_file or 'unknown'}",
        f"- Error diagnostics: {diag_lines}",
    ]
    if semantic_trigger:
        lines.append(f"- Semantic signal: {semantic_trigger}")
    lines += ["", f"Code snippet (→ = cursor line):\n```\n{snippet or '(unavailable)'}\n```"]

    try:
        response = await client.messages.create(
            model="claude-opus-4-8",
            max_tokens=768,
            system=SYSTEM_PROMPT,
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "trigger": {"type": "string"},
                            "root_cause": {"type": "string"},
                            "patch": {"type": "string"},
                            "patch_code": {"type": "string"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["trigger", "root_cause", "patch", "patch_code", "confidence"],
                        "additionalProperties": False,
                    },
                }
            },
            messages=[{"role": "user", "content": "\n".join(lines)}],
        )

        for block in response.content:
            if block.type == "text":
                return DiagnosisResult(**json.loads(block.text))
    except Exception:
        pass  # caller receives None and falls back to the generic overload message

    return None
