from contextlib import asynccontextmanager
from typing import AsyncGenerator

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI

import claude_client
import db
import scorer
from models import DiagnosisResult, TelemetryPayload, TelemetryResponse

# Rolling EWMA score lives here between requests. Loaded from the DB on startup
# so a server restart doesn't reset the score to zero.
_rolling_score: float = 0.0


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    global _rolling_score
    db.init_db()
    _rolling_score = await db.get_last_rolling_score()
    yield


app = FastAPI(title="FlowGuard Cognitive Engine", lifespan=lifespan)


@app.post("/telemetry", response_model=TelemetryResponse)
async def receive_telemetry(payload: TelemetryPayload) -> TelemetryResponse:
    global _rolling_score

    raw = scorer.instant_score(
        payload.backspaceCount,
        payload.fileSwitchCount,
        payload.errorCount,
    )
    _rolling_score = scorer.apply_ewma(_rolling_score, raw)
    score = round(min(_rolling_score, 100.0), 2)
    state = scorer.classify(score)

    diagnosis: DiagnosisResult | None = None
    if state == "OVERLOADED":
        diagnosis = await claude_client.get_diagnosis(
            score=score,
            backspace_count=payload.backspaceCount,
            file_switch_count=payload.fileSwitchCount,
            error_count=payload.errorCount,
            active_file=payload.activeFile,
            semantic_trigger=payload.semanticTrigger,
            diagnostics=payload.diagnostics,
            snippet=payload.snippet,
        )

    await db.insert_event(
        backspace_count=payload.backspaceCount,
        file_switch_count=payload.fileSwitchCount,
        error_count=payload.errorCount,
        active_file=payload.activeFile,
        semantic_trigger=payload.semanticTrigger,
        instant_score=raw,
        rolling_score=score,
        state=state,
        diagnosis=diagnosis,
    )

    return TelemetryResponse(score=score, state=state, diagnosis=diagnosis)


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "FlowGuard cognitive engine running"}
