import json
import os
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import anthropic
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="FlowGuard Cognitive Engine")

# Tuned against the 60s telemetry window emitted by the VS Code extension
# (see src/extension.ts LOG_INTERVAL_MS) — these are "per minute" spike ceilings.
BACKSPACE_SPIKE_THRESHOLD = 40
FILE_SWITCH_SPIKE_THRESHOLD = 8
ERROR_SPIKE_THRESHOLD = 5

# EWMA smoothing: how much a single sample can move the rolling score.
EWMA_ALPHA = 0.4

FLOW_UPPER_BOUND = 30
OVERLOADED_LOWER_BOUND = 70

FLOWGUARD_SYSTEM_PROMPT = """You are FlowGuard Core, an embedded cognitive-load intelligence engine for VS Code.

Given developer telemetry (deletion rate, file switches, error count, active file, diagnostics, code snippet), output a terse JSON diagnosis of the overload trigger.

Rules:
- Identify the ONE most likely cause from the available data
- patch must be actionable in under 30 seconds — a specific code edit or immediate action
- confidence (0.0–1.0) reflects how strongly the telemetry supports your diagnosis
- If no code snippet is available, diagnose from behavioral signals alone"""


class TelemetryPayload(BaseModel):
    backspaceCount: int = Field(ge=0)
    fileSwitchCount: int = Field(ge=0)
    errorCount: int = Field(ge=0)
    activeFile: Optional[str] = None
    snippet: Optional[str] = None
    diagnostics: Optional[list[str]] = None


class DiagnosisResult(BaseModel):
    trigger: str
    root_cause: str
    patch: str
    confidence: float


class TelemetryResponse(BaseModel):
    score: float
    state: str
    diagnosis: Optional[DiagnosisResult] = None


# Single-process, in-memory rolling state. Not shared across workers/processes
# and not partitioned per client — fine for a local single-developer engine.
_rolling_score = 0.0
_anthropic_client: Optional[anthropic.AsyncAnthropic] = None


def _get_client() -> Optional[anthropic.AsyncAnthropic]:
    global _anthropic_client
    if _anthropic_client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            _anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
    return _anthropic_client


def _instant_score(payload: TelemetryPayload) -> float:
    backspace_component = min(payload.backspaceCount / BACKSPACE_SPIKE_THRESHOLD, 1.0) * 55
    switch_component = min(payload.fileSwitchCount / FILE_SWITCH_SPIKE_THRESHOLD, 1.0) * 30
    error_component = min(payload.errorCount / ERROR_SPIKE_THRESHOLD, 1.0) * 15
    return backspace_component + switch_component + error_component


def _classify(score: float) -> str:
    if score < FLOW_UPPER_BOUND:
        return "FLOW"
    if score < OVERLOADED_LOWER_BOUND:
        return "NORMAL"
    return "OVERLOADED"


async def _call_claude_diagnosis(payload: TelemetryPayload, score: float) -> Optional[DiagnosisResult]:
    client = _get_client()
    if client is None:
        return None

    diag_lines = ", ".join(payload.diagnostics) if payload.diagnostics else "none"
    user_content = (
        f"Telemetry snapshot (score {score:.1f}/100 — OVERLOADED):\n"
        f"- Deletions last 60s: {payload.backspaceCount}\n"
        f"- File switches last 60s: {payload.fileSwitchCount}\n"
        f"- Workspace errors: {payload.errorCount}\n"
        f"- Active file: {payload.activeFile or 'unknown'}\n"
        f"- Error diagnostics: {diag_lines}\n\n"
        f"Code snippet (→ = cursor line):\n```\n{payload.snippet or '(unavailable)'}\n```"
    )

    response = await client.messages.create(
        model="claude-opus-4-8",
        max_tokens=512,
        system=FLOWGUARD_SYSTEM_PROMPT,
        output_config={
            "format": {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "trigger": {"type": "string"},
                        "root_cause": {"type": "string"},
                        "patch": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["trigger", "root_cause", "patch", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        messages=[{"role": "user", "content": user_content}],
    )

    for block in response.content:
        if block.type == "text":
            data = json.loads(block.text)
            return DiagnosisResult(**data)
    return None


@app.post("/telemetry", response_model=TelemetryResponse)
async def receive_telemetry(payload: TelemetryPayload) -> TelemetryResponse:
    global _rolling_score
    instant = _instant_score(payload)
    _rolling_score = (EWMA_ALPHA * instant) + ((1 - EWMA_ALPHA) * _rolling_score)
    score = round(min(_rolling_score, 100.0), 2)
    state = _classify(score)

    diagnosis = None
    if state == "OVERLOADED":
        diagnosis = await _call_claude_diagnosis(payload, score)

    return TelemetryResponse(score=score, state=state, diagnosis=diagnosis)


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "FlowGuard cognitive engine running"}
