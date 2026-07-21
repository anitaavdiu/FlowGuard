"""SQLite persistence layer.

Each telemetry POST is written as one row. The rolling EWMA score is
recovered from the last row on startup so a server restart doesn't
reset the score to zero.

All blocking sqlite3 calls are offloaded to a thread-pool via
asyncio.to_thread so the FastAPI event loop is never blocked.
"""

import asyncio
import sqlite3
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models import DiagnosisResult

DB_PATH = Path(__file__).parent / "flowguard.db"


def init_db() -> None:
    """Create the database and schema if they don't exist yet."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_events (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at       TEXT    NOT NULL DEFAULT (datetime('now')),
                backspace_count   INTEGER NOT NULL,
                file_switch_count INTEGER NOT NULL,
                error_count       INTEGER NOT NULL,
                active_file       TEXT,
                semantic_trigger  TEXT,
                instant_score     REAL    NOT NULL,
                rolling_score     REAL    NOT NULL,
                state             TEXT    NOT NULL,
                diag_trigger      TEXT,
                diag_root_cause   TEXT,
                diag_patch        TEXT,
                diag_patch_code   TEXT,
                diag_confidence   REAL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _last_rolling_score_sync() -> float:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT rolling_score FROM telemetry_events ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return float(row[0]) if row else 0.0
    finally:
        conn.close()


def _insert_event_sync(
    backspace_count: int,
    file_switch_count: int,
    error_count: int,
    active_file: Optional[str],
    semantic_trigger: Optional[str],
    instant_score: float,
    rolling_score: float,
    state: str,
    diagnosis: Optional["DiagnosisResult"],
) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            INSERT INTO telemetry_events (
                backspace_count, file_switch_count, error_count,
                active_file, semantic_trigger,
                instant_score, rolling_score, state,
                diag_trigger, diag_root_cause, diag_patch,
                diag_patch_code, diag_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                backspace_count,
                file_switch_count,
                error_count,
                active_file,
                semantic_trigger,
                instant_score,
                rolling_score,
                state,
                diagnosis.trigger if diagnosis else None,
                diagnosis.root_cause if diagnosis else None,
                diagnosis.patch if diagnosis else None,
                diagnosis.patch_code if diagnosis else None,
                diagnosis.confidence if diagnosis else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


async def get_last_rolling_score() -> float:
    return await asyncio.to_thread(_last_rolling_score_sync)


async def insert_event(
    backspace_count: int,
    file_switch_count: int,
    error_count: int,
    active_file: Optional[str],
    semantic_trigger: Optional[str],
    instant_score: float,
    rolling_score: float,
    state: str,
    diagnosis: Optional["DiagnosisResult"] = None,
) -> None:
    await asyncio.to_thread(
        _insert_event_sync,
        backspace_count,
        file_switch_count,
        error_count,
        active_file,
        semantic_trigger,
        instant_score,
        rolling_score,
        state,
        diagnosis,
    )
