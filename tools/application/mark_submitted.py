"""Mark a staged application as submitted. Idempotent — refuses if already marked."""
from __future__ import annotations
import argparse, csv, json, logging, sys
from datetime import datetime, timezone
from pathlib import Path

APPS_ROOT = Path("temp/outputs/applications")
CSV_PATH = APPS_ROOT / "applications.csv"

log = logging.getLogger(__name__)

def _find_folder(job_id: str) -> Path:
    matches = list(APPS_ROOT.glob(f"{job_id}__*"))
    if not matches:
        raise RuntimeError(f"no staged application for job_id={job_id}")
    return matches[0]

def mark_submitted(job_id: str, notes: str | None = None) -> str:
    folder = _find_folder(job_id)
    marker = folder / "submitted.json"
    if marker.exists():
        raise RuntimeError(f"{job_id} already marked submitted at {marker}")
    now = datetime.now(timezone.utc).isoformat()
    marker.write_text(json.dumps({"submitted_at": now, "notes": notes or ""}, indent=2))
    # Update CSV row
    if CSV_PATH.exists():
        rows = list(csv.reader(CSV_PATH.read_text().splitlines()))
        header, *data = rows
        for r in data:
            if r and r[0] == job_id:
                r[3] = "submitted"
                r[5] = now
        with CSV_PATH.open("w", newline="") as f:
            w = csv.writer(f); w.writerow(header); w.writerows(data)

    # Mirror to SQLite for the dashboard. Guarded — CSV is durable source of truth.
    try:
        from tools.db import store as db_store
        conn = db_store.init_db(db_store.DEFAULT_DB_PATH)
        try:
            db_store.set_status(conn, job_id, "submitted")
        finally:
            conn.close()
    except Exception:
        log.warning("DB mirror failed for submitted job %s — CSV log is intact", job_id, exc_info=True)

    return str(folder)

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("job_id")
    p.add_argument("--notes", default=None)
    args = p.parse_args()
    print(mark_submitted(args.job_id, notes=args.notes))
    return 0

if __name__ == "__main__":
    sys.exit(main())
