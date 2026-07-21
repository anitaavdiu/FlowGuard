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


class TelemetryPayload(BaseModel):
    backspaceCount: int = Field(ge=0)
    fileSwitchCount: int = Field(ge=0)
    errorCount: int = Field(ge=0)


class TelemetryResponse(BaseModel):
    score: float
    state: str


# Single-process, in-memory rolling state. Not shared across workers/processes
# and not partitioned per client — fine for a local single-developer engine.
_rolling_score = 0.0


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


@app.post("/telemetry", response_model=TelemetryResponse)
def receive_telemetry(payload: TelemetryPayload) -> TelemetryResponse:
    global _rolling_score
    instant = _instant_score(payload)
    _rolling_score = (EWMA_ALPHA * instant) + ((1 - EWMA_ALPHA) * _rolling_score)
    score = round(min(_rolling_score, 100.0), 2)
    return TelemetryResponse(score=score, state=_classify(score))


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "FlowGuard cognitive engine running"}
