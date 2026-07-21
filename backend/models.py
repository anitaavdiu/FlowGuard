from typing import Optional

from pydantic import BaseModel, Field


class TelemetryPayload(BaseModel):
    backspaceCount: int = Field(ge=0)
    fileSwitchCount: int = Field(ge=0)
    errorCount: int = Field(ge=0)
    activeFile: Optional[str] = None
    snippet: Optional[str] = None
    diagnostics: Optional[list[str]] = None
    semanticTrigger: Optional[str] = None


class DiagnosisResult(BaseModel):
    trigger: str
    root_cause: str
    patch: str
    patch_code: str  # actual code to insert; empty string when no direct insertion applies
    confidence: float


class TelemetryResponse(BaseModel):
    score: float
    state: str
    diagnosis: Optional[DiagnosisResult] = None
