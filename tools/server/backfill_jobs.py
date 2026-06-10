"""In-memory single-slot tracker for the long-running backfill workflow.

The dashboard's "Backfill" button kicks off a BackgroundTask that walks every
page of LinkedIn results — minutes long for a 4-day window. We expose the
current state via GET /api/workflow/status so the UI can show progress.

Only one backfill can run at a time (resource discipline + LinkedIn throttle).
Concurrent POSTs are rejected with 409.
"""
from __future__ import annotations
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.db import store as db_store
from tools.workflow import search as backfill_workflow


_lock = threading.Lock()
_state: dict[str, Any] = {
    "state": "idle",                # 'idle' | 'running' | 'done' | 'error'
    "phase": None,                  # current phase reported by orchestrator
    "phase_payload": None,
    "started_at": None,
    "finished_at": None,
    "stats": None,                  # final BackfillStats dict
    "error": None,
}


def get_state() -> dict:
    with _lock:
        return dict(_state)


def is_running() -> bool:
    with _lock:
        return _state["state"] == "running"


def _set(**fields) -> None:
    with _lock:
        _state.update(fields)


def run_backfill_safely(
    *,
    keywords: str,
    location: str | None,
    location_geo_id: str | None,
    days_back: int,
    threshold: float,
    db_path: Path,
    profile_path: Path,
) -> None:
    """Wrapper for use as a FastAPI BackgroundTask. Updates the tracker."""
    _set(
        state="running",
        phase="starting",
        phase_payload=None,
        started_at=datetime.utcnow().isoformat() + "Z",
        finished_at=None,
        stats=None,
        error=None,
    )

    def on_progress(phase: str, payload: dict) -> None:
        _set(phase=phase, phase_payload=payload)

    try:
        stats = backfill_workflow.run_backfill(
            keywords=keywords,
            location=location,
            location_geo_id=location_geo_id,
            days_back=days_back,
            threshold=threshold,
            db_path=db_path,
            profile_path=profile_path,
            on_progress=on_progress,
        )
        _set(
            state="done",
            phase="done",
            phase_payload=stats.as_dict(),
            stats=stats.as_dict(),
            finished_at=datetime.utcnow().isoformat() + "Z",
        )
    except Exception as e:
        _set(
            state="error",
            phase=None,
            phase_payload=None,
            error=str(e),
            finished_at=datetime.utcnow().isoformat() + "Z",
        )
        raise
