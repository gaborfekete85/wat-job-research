"""Background PDF rendering for the dashboard.

The 'Generate PDF' button triggers a long-ish (~5-8s) pipeline:
  tailor → render_with_source_header → stage_application.

We track per-job state in an in-memory registry. The dashboard polls
GET /api/jobs/{id}/pdf-status until 'done' or 'error'.

No Celery / Redis — this is a single-user local app. A dict + lock is enough.
"""
from __future__ import annotations
import json
import logging
import tempfile
import threading
from pathlib import Path

from tools.db import store as db_store
from tools.cv import tailor as cv_tailor
from tools.cv import render_with_source_header as cv_render
from tools.application import stage as app_stage

log = logging.getLogger(__name__)

# In-memory state: {job_id: 'running' | 'done' | 'error:<msg>'}
_state: dict[str, str] = {}
_lock = threading.Lock()


def get_state(job_id: str) -> str:
    with _lock:
        return _state.get(job_id, "idle")


def set_state(job_id: str, value: str) -> None:
    with _lock:
        _state[job_id] = value


def clear_state(job_id: str) -> None:
    with _lock:
        _state.pop(job_id, None)


def _latest_source_pdf(resources_dir: Path) -> Path:
    """Return the user's source CV PDF (with QR codes / header to preserve).

    Canonical filename: profile/cv_source.pdf.
    """
    canonical = resources_dir / "cv_source.pdf"
    if canonical.is_file():
        return canonical
    # Back-compat: pick the most recent *.pdf in the directory.
    candidates = sorted(p for p in resources_dir.glob("*.pdf") if p.is_file())
    if not candidates:
        raise FileNotFoundError(
            f"no source CV found in {resources_dir} (expected cv_source.pdf)"
        )
    return candidates[-1]


def run_pdf_pipeline(
    job_id: str,
    *,
    db_path: Path,
    profile_path: Path,
    resources_dir: Path,
) -> Path:
    """Run tailor + render + stage for one job. Writes the tailored PDF + updates DB.

    Returns the absolute path to the generated PDF.
    Raises on any failure — caller is responsible for setting error state.
    """
    set_state(job_id, "running")
    try:
        conn = db_store.init_db(db_path)
        try:
            job = db_store.get_job(conn, job_id)
            if job is None:
                raise RuntimeError(f"job {job_id} not found in DB")
            match_json = job.get("match_result_json")
            if not match_json:
                raise RuntimeError(f"job {job_id} has no match_result_json — needs LLM scoring first")
            match_result = json.loads(match_json)

            source_pdf = _latest_source_pdf(resources_dir)
            profile_md = profile_path.read_text()

            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                # 1. Tailor YAML
                tailored_yml = tmp / "tailored.yml"
                tailored_yml.write_text(cv_tailor.tailor(profile_md, match_result))

                # 2. Render PDF (body via WeasyPrint + source header via pymupdf)
                tailored_pdf = tmp / "tailored_cv.pdf"
                cv_render.compose(source_pdf, tailored_yml, tailored_pdf)

                # 3. Stage application (creates folder under temp/outputs/applications/)
                #    This also writes DB rows via the modified stage_application.
                job_payload = {
                    "job_id": job["id"],
                    "title": job["title"],
                    "company": job["company"],
                    "location": job["location"],
                    "url": job["link"],
                    "apply_url": job["apply_url"],
                    "description": job["description"],
                }
                folder = app_stage.stage_application(
                    job_payload,
                    cv_pdf=tailored_pdf,
                    match_result=match_result,
                )
                final_pdf = Path(folder) / "tailored_cv.pdf"

            # The stage helper handles DB writes; this is belt+suspenders.
            db_store.set_tailored_pdf(conn, job_id, final_pdf)
            db_store.set_status(conn, job_id, "staged")
            set_state(job_id, "done")
            return final_pdf
        finally:
            conn.close()
    except Exception as e:
        log.exception("PDF pipeline failed for %s", job_id)
        set_state(job_id, f"error:{e}")
        raise
