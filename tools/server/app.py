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
from tools.linkedin import resolve_location
from tools.server import backfill_jobs, pdf_jobs

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
PROFILE_DIR = PROJECT_ROOT / "profile"
PROFILE_PATH = PROFILE_DIR / "profile.md"
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
        """Accepts a partial dict of preferences. A null/empty value on a
        clearable key (e.g. `location_geo_id`) deletes that row.
        """
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

    @app.post("/api/workflow/search", status_code=202)
    def start_backfill(payload: dict, background: BackgroundTasks) -> dict:
        """Kick off a backfill: walk all pages of LinkedIn results over the last
        N days and ingest jobs whose keyword score >= threshold (skipping any
        already in the DB)."""
        if backfill_jobs.is_running():
            raise HTTPException(409, detail={
                "error": "backfill_already_running",
                "message": "A backfill is already in progress. Poll /api/workflow/status.",
            })
        days_back = int(payload.get("days_back", 4))
        threshold = float(payload.get("threshold", 0.7))
        if not (1 <= days_back <= 30):
            raise HTTPException(400, "days_back must be between 1 and 30")
        if not (0.0 <= threshold <= 1.0):
            raise HTTPException(400, "threshold must be between 0.0 and 1.0")

        conn = _conn()
        try:
            prefs = db_store.get_preferences(conn)
        finally:
            conn.close()
        keywords = payload.get("keywords") or prefs.get("keywords")
        location = payload.get("location") or prefs.get("location")
        geo_id = payload.get("location_geo_id") or prefs.get("location_geo_id")
        if not keywords:
            raise HTTPException(400, "keywords missing (none in payload or DB preference)")

        background.add_task(
            backfill_jobs.run_backfill_safely,
            keywords=keywords,
            location=location,
            location_geo_id=geo_id,
            days_back=days_back,
            threshold=threshold,
            db_path=app.state.db_path,
            profile_path=PROFILE_PATH,
        )
        return {"state": "running", "days_back": days_back, "threshold": threshold,
                "keywords": keywords, "location_geo_id": geo_id}

    @app.get("/api/workflow/status")
    def get_backfill_status() -> dict:
        return backfill_jobs.get_state()

    @app.get("/api/locations/typeahead")
    def location_typeahead(q: str) -> list[dict]:
        """Proxy LinkedIn's public typeahead so the dashboard can show a
        confirm-on-pick dropdown. Returns top 10 hits with id + displayName.
        """
        q = (q or "").strip()
        if len(q) < 2:
            return []
        try:
            return resolve_location.resolve(q)
        except Exception as e:
            log.warning("typeahead failed for %r: %s", q, e)
            raise HTTPException(502, detail={"error": "typeahead_failed", "message": str(e)})

    @app.get("/api/jobs")
    def list_jobs() -> dict:
        """Triage buckets only. Filtered-out jobs are a separate concern —
        fetch them via /api/jobs/filtered to keep this response lean.
        """
        conn = _conn()
        try:
            new = [_row_to_summary(r) for r in db_store.list_jobs(conn, status="new")]
            viewed = [_row_to_summary(r) for r in db_store.list_jobs(conn, status="viewed")]
            staged = [_row_to_summary(r) for r in db_store.list_jobs(conn, status="staged")]
            submitted = [_row_to_summary(r) for r in db_store.list_jobs(conn, status="submitted")]
            # Count only — content streamed via /api/jobs/filtered to keep
            # the main response small even after big backfills.
            filtered_count = len(db_store.list_jobs(conn, status="filtered_out"))
            return {
                "new": new,
                "viewed": viewed,
                "staged": staged,
                "submitted": submitted,
                "filtered_out_count": filtered_count,
            }
        finally:
            conn.close()

    @app.get("/api/jobs/filtered")
    def list_filtered_jobs() -> list[dict]:
        """All jobs the backfill kept aside because their keyword similarity
        was below the threshold. Sorted by score DESC so the near-misses
        (the ones most worth promoting back to NEW) appear first.
        """
        conn = _conn()
        try:
            rows = db_store.list_jobs(conn, status="filtered_out")
            rows.sort(key=lambda r: (r.get("keyword_score") or 0), reverse=True)
            return [_row_to_summary(r) for r in rows]
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

    @app.post("/api/jobs/{job_id}/status")
    def set_job_status(job_id: str, payload: dict) -> dict:
        """Generic status transition — used by the dashboard's drag-and-drop.
        Body: {"status": "new"|"viewed"|"staged"|"submitted"|"dismissed"}.
        """
        target = (payload or {}).get("status")
        if not target:
            raise HTTPException(400, detail="`status` field is required")
        conn = _conn()
        try:
            row = db_store.get_job(conn, job_id)
            if row is None:
                raise HTTPException(404, f"job {job_id} not found")
            try:
                db_store.set_status(conn, job_id, target)
            except ValueError as e:
                raise HTTPException(400, detail=str(e))
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
            resources_dir=PROFILE_DIR,
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
