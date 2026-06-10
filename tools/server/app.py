"""FastAPI app: REST API + dashboard for the WAT job-search project.

Run:
    python -m tools.server
Then visit http://localhost:8765 in a browser.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from tools.db import store as db_store
from tools.server import pdf_jobs

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
PROFILE_PATH = PROJECT_ROOT / "temp" / "resources" / "profile.md"
RESOURCES_DIR = PROJECT_ROOT / "temp" / "resources"
DB_PATH = Path(os.environ.get("WAT_DB_PATH", PROJECT_ROOT / "temp" / "outputs" / "jobs.db"))


def _row_to_summary(row: dict) -> dict:
    """Compact row for the listing endpoint (drops the verbose description + JSON)."""
    return {
        "id": row["id"],
        "title": row["title"],
        "company": row["company"],
        "location": row["location"],
        "link": row["link"],
        "apply_url": row["apply_url"],
        "keyword_score": row["keyword_score"],
        "llm_final_score": row["llm_final_score"],
        "has_match_result": bool(row.get("match_result_json")),
        "tailored_pdf_path": row["tailored_pdf_path"],
        "status": row["status"],
        "discovered_at": row["discovered_at"],
        "viewed_at": row["viewed_at"],
        "staged_at": row["staged_at"],
        "submitted_at": row["submitted_at"],
    }


def create_app(db_path: Path = DB_PATH) -> FastAPI:
    app = FastAPI(title="WAT Job Search")
    app.state.db_path = db_path

    def _conn():
        return db_store.init_db(app.state.db_path)

    @app.get("/api/preferences")
    def get_prefs() -> dict:
        conn = _conn()
        try:
            return db_store.get_preferences(conn)
        finally:
            conn.close()

    @app.put("/api/preferences")
    def update_prefs(payload: dict) -> dict:
        conn = _conn()
        try:
            errors = {}
            for key, value in payload.items():
                try:
                    db_store.set_preference(conn, key, value)
                except ValueError as e:
                    errors[key] = str(e)
            if errors:
                raise HTTPException(400, detail={"error": "invalid_preferences", "fields": errors})
            return db_store.get_preferences(conn)
        finally:
            conn.close()

    @app.get("/api/jobs")
    def list_jobs() -> dict:
        conn = _conn()
        try:
            new = [_row_to_summary(r) for r in db_store.list_jobs(conn, status="new")]
            viewed = [_row_to_summary(r) for r in db_store.list_jobs(conn, status="viewed")]
            staged = [_row_to_summary(r) for r in db_store.list_jobs(conn, status="staged")]
            submitted = [_row_to_summary(r) for r in db_store.list_jobs(conn, status="submitted")]
            return {
                "new": new,
                "viewed": viewed,
                "staged": staged,
                "submitted": submitted,
            }
        finally:
            conn.close()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        conn = _conn()
        try:
            row = db_store.get_job(conn, job_id)
            if row is None:
                raise HTTPException(404, f"job {job_id} not found")
            # Parse match_result_json into a real object for the client.
            if row.get("match_result_json"):
                row["match_result"] = json.loads(row["match_result_json"])
            return row
        finally:
            conn.close()

    @app.post("/api/jobs/{job_id}/view")
    def mark_viewed(job_id: str) -> dict:
        conn = _conn()
        try:
            row = db_store.get_job(conn, job_id)
            if row is None:
                raise HTTPException(404, f"job {job_id} not found")
            if row["status"] == "new":
                db_store.set_status(conn, job_id, "viewed")
            return _row_to_summary(db_store.get_job(conn, job_id))
        finally:
            conn.close()

    @app.post("/api/jobs/{job_id}/dismiss")
    def dismiss(job_id: str) -> dict:
        conn = _conn()
        try:
            row = db_store.get_job(conn, job_id)
            if row is None:
                raise HTTPException(404, f"job {job_id} not found")
            db_store.set_status(conn, job_id, "dismissed")
            return _row_to_summary(db_store.get_job(conn, job_id))
        finally:
            conn.close()

    @app.post("/api/jobs/{job_id}/generate-pdf", status_code=202)
    def generate_pdf(job_id: str, background: BackgroundTasks) -> dict:
        conn = _conn()
        try:
            row = db_store.get_job(conn, job_id)
            if row is None:
                raise HTTPException(404, f"job {job_id} not found")
            if not row.get("match_result_json"):
                raise HTTPException(
                    409,
                    detail={
                        "error": "needs_llm_scoring",
                        "message": f"job {job_id} has no match result — run LLM scoring first.",
                    },
                )
            current = pdf_jobs.get_state(job_id)
            if current == "running":
                return {"job_id": job_id, "state": "running", "already_running": True}
        finally:
            conn.close()

        pdf_jobs.set_state(job_id, "running")
        background.add_task(
            _run_pdf_safely,
            job_id=job_id,
            db_path=app.state.db_path,
            profile_path=PROFILE_PATH,
            resources_dir=RESOURCES_DIR,
        )
        return {"job_id": job_id, "state": "running"}

    @app.get("/api/jobs/{job_id}/pdf-status")
    def pdf_status(job_id: str) -> dict:
        return {"job_id": job_id, "state": pdf_jobs.get_state(job_id)}

    @app.get("/pdfs/{job_id}.pdf")
    def serve_pdf(job_id: str) -> FileResponse:
        conn = _conn()
        try:
            row = db_store.get_job(conn, job_id)
        finally:
            conn.close()
        if row is None or not row.get("tailored_pdf_path"):
            raise HTTPException(404, f"no tailored PDF for {job_id}")
        path = Path(row["tailored_pdf_path"])
        if not path.exists():
            raise HTTPException(404, f"PDF file missing on disk: {path}")
        return FileResponse(str(path), media_type="application/pdf",
                            filename=f"tailored_cv_{job_id}.pdf")

    # Dashboard (mounted last so /api/* routes win)
    if DASHBOARD_DIR.exists():
        app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")

    return app


def _run_pdf_safely(*, job_id: str, db_path: Path, profile_path: Path, resources_dir: Path) -> None:
    """Background task wrapper — swallows exceptions so the worker doesn't die."""
    try:
        pdf_jobs.run_pdf_pipeline(
            job_id,
            db_path=db_path,
            profile_path=profile_path,
            resources_dir=resources_dir,
        )
    except Exception:
        # run_pdf_pipeline already sets state to 'error:<msg>'; just log + swallow.
        log.exception("background PDF task failed for %s", job_id)


app = create_app()
