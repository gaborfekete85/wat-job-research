"""Mark a staged application as submitted. Idempotent — refuses if already marked."""
from __future__ import annotations
import argparse, csv, json, sys
from datetime import datetime, timezone
from pathlib import Path

APPS_ROOT = Path("temp/outputs/applications")
CSV_PATH = APPS_ROOT / "applications.csv"

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
