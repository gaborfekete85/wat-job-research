"""CLI: ingest a jobs JSON file (from a pipeline run) into the jobs.db SQLite store.

Used by the workflow after LLM scoring (or after keyword filtering, if no API key).
Upserts every job — new ones land in 'new' status; existing ones get their content
and scores refreshed without changing status or discovered_at.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from tools.db.store import DEFAULT_DB_PATH, init_db, upsert_job


def ingest_file(jobs_path: Path, db_path: Path = DEFAULT_DB_PATH) -> tuple[int, int]:
    """Upsert every job in the JSON list. Returns (inserted_count, updated_count)."""
    payload = json.loads(jobs_path.read_text())
    if not isinstance(payload, list):
        raise SystemExit(f"expected a JSON list of jobs at {jobs_path}, got {type(payload).__name__}")

    conn = init_db(db_path)
    inserted = updated = 0
    for job in payload:
        cur = conn.execute("SELECT id FROM jobs WHERE id = ?", (str(job["job_id"]),))
        existed = cur.fetchone() is not None
        upsert_job(conn, job)
        if existed:
            updated += 1
        else:
            inserted += 1
    conn.close()
    return inserted, updated


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jobs", required=True, help="path to JSON list of jobs (e.g. jobs_filtered.json or jobs_matched.json)")
    p.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = p.parse_args()
    inserted, updated = ingest_file(Path(args.jobs), Path(args.db))
    print(f"  inserted: {inserted}  updated: {updated}  → {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
