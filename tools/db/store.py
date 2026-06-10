"""SQLite store for discovered jobs. Single table, stdlib sqlite3 — no ORM."""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB_PATH = Path("temp/outputs/jobs.db")

ALLOWED_STATUSES = {"new", "viewed", "staged", "submitted", "dismissed"}


def init_db(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a connection and ensure the schema exists. Idempotent."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_to_row(job: dict) -> dict:
    """Normalize a job dict (as produced by the pipeline) into a row dict."""
    keyword_score = None
    if isinstance(job.get("keyword_score"), dict):
        keyword_score = job["keyword_score"].get("score")
    elif isinstance(job.get("keyword_score"), (int, float)):
        keyword_score = float(job["keyword_score"])

    llm_score = None
    match_result_json = None
    if isinstance(job.get("llm_score"), dict):
        llm_score = job["llm_score"].get("final_score")
        match_result_json = json.dumps(job["llm_score"], ensure_ascii=False)
    elif isinstance(job.get("match_result"), dict):
        llm_score = job["match_result"].get("final_score")
        match_result_json = json.dumps(job["match_result"], ensure_ascii=False)

    return {
        "id": str(job["job_id"]),
        "title": job.get("title") or "",
        "company": job.get("company") or "",
        "location": job.get("location"),
        "description": job.get("description") or "",
        "link": job.get("url") or "",
        "apply_url": job.get("apply_url"),
        "keyword_score": keyword_score,
        "llm_final_score": llm_score,
        "match_result_json": match_result_json,
    }


def upsert_job(conn: sqlite3.Connection, job: dict) -> str:
    """Insert or update a job. Returns the canonical job_id.

    On insert: status='new', discovered_at = now.
    On update: keeps existing status/discovered_at; refreshes content fields and scores
    if the new payload has them (non-null scores override; null does NOT clobber).
    """
    row = _job_to_row(job)
    job_id = row["id"]
    cur = conn.cursor()
    existing = cur.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()

    if existing is None:
        cur.execute(
            """
            INSERT INTO jobs (
                id, title, company, location, description, link, apply_url,
                keyword_score, llm_final_score, match_result_json,
                status, discovered_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
            """,
            (
                row["id"], row["title"], row["company"], row["location"],
                row["description"], row["link"], row["apply_url"],
                row["keyword_score"], row["llm_final_score"], row["match_result_json"],
                _now_iso(),
            ),
        )
    else:
        # Update content + scores, but don't clobber non-null values with NULL
        # and don't touch status/discovered_at/viewed_at/staged_at/submitted_at.
        sets = [
            "title = ?", "company = ?", "location = ?",
            "description = ?", "link = ?", "apply_url = ?",
        ]
        params: list[Any] = [
            row["title"], row["company"], row["location"],
            row["description"], row["link"], row["apply_url"],
        ]
        if row["keyword_score"] is not None:
            sets.append("keyword_score = ?")
            params.append(row["keyword_score"])
        if row["llm_final_score"] is not None:
            sets.append("llm_final_score = ?")
            params.append(row["llm_final_score"])
        if row["match_result_json"] is not None:
            sets.append("match_result_json = ?")
            params.append(row["match_result_json"])
        params.append(job_id)
        cur.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", params)

    conn.commit()
    return job_id


def list_jobs(conn: sqlite3.Connection, status: str | None = None) -> list[dict]:
    """Return jobs as plain dicts. If status is given, filter to that status."""
    if status:
        cur = conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY discovered_at DESC",
            (status,),
        )
    else:
        cur = conn.execute("SELECT * FROM jobs ORDER BY discovered_at DESC")
    return [dict(r) for r in cur.fetchall()]


def get_job(conn: sqlite3.Connection, job_id: str) -> dict | None:
    cur = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def set_status(conn: sqlite3.Connection, job_id: str, status: str) -> None:
    if status not in ALLOWED_STATUSES:
        raise ValueError(
            f"invalid status {status!r}; allowed: {sorted(ALLOWED_STATUSES)}"
        )
    timestamp_col = {
        "viewed": "viewed_at",
        "staged": "staged_at",
        "submitted": "submitted_at",
    }.get(status)
    if timestamp_col:
        conn.execute(
            f"UPDATE jobs SET status = ?, {timestamp_col} = COALESCE({timestamp_col}, ?) "
            "WHERE id = ?",
            (status, _now_iso(), job_id),
        )
    else:
        conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
    conn.commit()


def set_tailored_pdf(conn: sqlite3.Connection, job_id: str, path: Path) -> None:
    conn.execute(
        "UPDATE jobs SET tailored_pdf_path = ? WHERE id = ?",
        (str(path), job_id),
    )
    conn.commit()
