"""Stage an application: create per-job folder, copy artifacts, append CSV row."""
from __future__ import annotations
import argparse, csv, json, logging, re, shutil, sys
from datetime import datetime, timezone
from pathlib import Path

APPS_ROOT = Path("temp/outputs/applications")
CSV_PATH = APPS_ROOT / "applications.csv"
CSV_HEADER = ["job_id", "company", "title", "status", "staged_at", "submitted_at", "folder"]

log = logging.getLogger(__name__)

def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:50] or "untitled"

def stage_application(job: dict, *, cv_pdf: Path,
                      cover_letter_md: Path | None = None,
                      cover_letter_pdf: Path | None = None,
                      ats_answers_md: Path | None = None,
                      match_result: dict | None = None) -> str:
    job_id = str(job["job_id"])
    folder = APPS_ROOT / f"{job_id}__{_slug(job.get('company') or 'unknown')}__{_slug(job.get('title') or 'untitled')}"
    if folder.exists():
        # Idempotency: stage is a no-op if already staged
        return str(folder)
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "job_details.json").write_text(json.dumps(job, indent=2, ensure_ascii=False))
    if match_result:
        (folder / "match_result.json").write_text(json.dumps(match_result, indent=2, ensure_ascii=False))
    shutil.copy(cv_pdf, folder / "tailored_cv.pdf")
    if cover_letter_md: shutil.copy(cover_letter_md, folder / "cover_letter.md")
    if cover_letter_pdf: shutil.copy(cover_letter_pdf, folder / "cover_letter.pdf")
    if ats_answers_md: shutil.copy(ats_answers_md, folder / "ats_answers.md")
    apply_url = job.get("apply_url") or job.get("url") or ""
    (folder / "apply_url.txt").write_text(apply_url + "\n")

    APPS_ROOT.mkdir(parents=True, exist_ok=True)
    new_file = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="") as f:
        w = csv.writer(f)
        if new_file: w.writerow(CSV_HEADER)
        w.writerow([job_id, job.get("company") or "", job.get("title") or "",
                    "staged", datetime.now(timezone.utc).isoformat(), "", str(folder)])

    # Mirror to SQLite for the dashboard. Guarded — the CSV log is the durable
    # source of truth; a DB write failure must NOT break staging.
    try:
        from tools.db import store as db_store
        conn = db_store.init_db(db_store.DEFAULT_DB_PATH)
        try:
            existing = db_store.get_job(conn, job_id)
            if existing is None:
                # Upsert a minimal row from the job dict so the dashboard sees it.
                db_store.upsert_job(conn, {**job, "url": job.get("url") or ""})
            db_store.set_tailored_pdf(conn, job_id, folder / "tailored_cv.pdf")
            db_store.set_status(conn, job_id, "staged")
        finally:
            conn.close()
    except Exception:
        log.warning("DB mirror failed for staged job %s — CSV log is intact", job_id, exc_info=True)

    return str(folder)

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--job-details", required=True)
    p.add_argument("--cv", required=True)
    p.add_argument("--cover-letter", default=None)
    p.add_argument("--cover-letter-pdf", default=None)
    p.add_argument("--ats-answers", default=None)
    p.add_argument("--match-result", default=None)
    args = p.parse_args()
    job = json.loads(Path(args.job_details).read_text())
    match = json.loads(Path(args.match_result).read_text()) if args.match_result else None
    folder = stage_application(
        job, cv_pdf=Path(args.cv),
        cover_letter_md=Path(args.cover_letter) if args.cover_letter else None,
        cover_letter_pdf=Path(args.cover_letter_pdf) if args.cover_letter_pdf else None,
        ats_answers_md=Path(args.ats_answers) if args.ats_answers else None,
        match_result=match,
    )
    print(folder)
    return 0

if __name__ == "__main__":
    sys.exit(main())
