"""Backfill orchestrator: search LinkedIn, score keywords, ingest with dedup.

Walks every page of LinkedIn search results for the configured keywords +
location over the last N days, applies a keyword similarity threshold, and
inserts ONLY jobs not already in the database. Existing rows are left
entirely untouched (status, scores, timestamps — all preserved).

Callable from CLI:
    python -m tools.workflow.search --days 4 --threshold 0.7

…and from the FastAPI server's `POST /api/workflow/search` background task.
"""
from __future__ import annotations
import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from tools.db import store as db_store
from tools.linkedin import resolve_location, search_jobs, get_job_details
from tools.match.extract_skills import extract_from_profile_yaml, extract_from_text
from tools.match.score_keyword import score as score_keyword

log = logging.getLogger(__name__)

DEFAULT_DAYS_BACK = 4
DEFAULT_THRESHOLD = 0.5            # below this keyword score, jobs go to filtered_out
DEFAULT_MAX_RESULTS = 500          # safety cap; LinkedIn rarely returns this much
CACHE_DIR = Path("temp/outputs/cache")

ProgressCb = Callable[[str, dict], None] | None


@dataclass
class BackfillStats:
    """Final counts reported by run_backfill()."""
    total_found: int = 0              # jobs returned by LinkedIn search
    skipped_existing: int = 0         # already in DB → untouched
    inserted: int = 0                 # above threshold → status='new'
    inserted_filtered_out: int = 0    # below threshold → status='filtered_out'
                                       #   (kept for later review on the
                                       #    Filtered Out dashboard page)
    fetch_failures: int = 0
    elapsed_seconds: float = 0.0
    threshold: float = DEFAULT_THRESHOLD
    days_back: int = DEFAULT_DAYS_BACK

    def as_dict(self) -> dict:
        return {
            "total_found": self.total_found,
            "skipped_existing": self.skipped_existing,
            "inserted": self.inserted,
            "inserted_filtered_out": self.inserted_filtered_out,
            "fetch_failures": self.fetch_failures,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "threshold": self.threshold,
            "days_back": self.days_back,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_job_detail(job_id: str) -> dict:
    """Return the JD detail from cache if present, else hit LinkedIn + cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{job_id}.json"
    if cache.exists():
        try:
            cached = json.loads(cache.read_text())
            if cached.get("job_detail"):
                return cached["job_detail"]
        except json.JSONDecodeError:
            pass
    detail = get_job_details.fetch(job_id)
    cache.write_text(json.dumps({"job_detail": detail, "cached_at": _now_iso()},
                                indent=2, ensure_ascii=False))
    return detail


def run_backfill(
    *,
    keywords: str,
    location: str | None = None,
    location_geo_id: str | None = None,
    days_back: int = DEFAULT_DAYS_BACK,
    threshold: float = DEFAULT_THRESHOLD,
    max_results: int = DEFAULT_MAX_RESULTS,
    db_path: Path = db_store.DEFAULT_DB_PATH,
    profile_path: Path = Path("profile/profile.md"),
    on_progress: ProgressCb = None,
) -> BackfillStats:
    """Search LinkedIn, score keywords, insert only new jobs above threshold.

    `on_progress(phase, payload)` is called at each phase boundary so the
    caller (CLI or API background task) can update its view. Phases:
      "resolving"  payload: {location, location_geo_id}
      "searching"  payload: {keywords, geo_id, days_back, max_results}
      "scoring"    payload: {current, total, last_job_id}
      "done"       payload: stats.as_dict()
    """
    started = datetime.now()
    stats = BackfillStats(threshold=threshold, days_back=days_back)
    progress = on_progress or (lambda *_: None)

    # 1. Resolve location to a geoId (prefer the stored confirmed one)
    geo_id = location_geo_id
    progress("resolving", {"location": location, "location_geo_id": geo_id})
    if not geo_id:
        if not location:
            raise ValueError("either location or location_geo_id must be provided")
        hits = resolve_location.resolve(location)
        if not hits:
            raise RuntimeError(f"no LinkedIn geo hits for {location!r}")
        geo_id = hits[0]["id"]
        log.info("resolved %r → geoId %s (%s)", location, geo_id, hits[0]["displayName"])

    # 2. Read profile skills (used once per run)
    profile_md = profile_path.read_text()
    profile_skills = extract_from_profile_yaml(profile_md)

    # 3. Paginated search
    posted_within_hours = days_back * 24
    progress("searching", {"keywords": keywords, "geo_id": geo_id,
                            "days_back": days_back, "max_results": max_results})
    summaries = search_jobs.search(
        keywords, geo_id,
        posted_within_hours=posted_within_hours,
        limit=max_results,
    )
    stats.total_found = len(summaries)

    # 4. Open DB once; close in finally
    conn = db_store.init_db(db_path)
    try:
        for i, summary in enumerate(summaries):
            jid = summary["job_id"]
            progress("scoring", {"current": i + 1, "total": len(summaries), "last_job_id": jid})

            # Cross-check on DB: skip entirely if already known
            if db_store.get_job(conn, jid) is not None:
                stats.skipped_existing += 1
                continue

            # Detail (cache-aware) + keyword score
            try:
                detail = _fetch_job_detail(jid)
            except Exception:
                log.warning("failed to fetch details for %s", jid, exc_info=True)
                stats.fetch_failures += 1
                continue

            full = {**summary, **detail}
            jd_skills = extract_from_text(full.get("description") or "")
            ks = score_keyword(profile_skills, jd_skills)
            full["keyword_score"] = ks

            # Above threshold → status='new' (main triage flow).
            # Below threshold → status='filtered_out' (kept for later review
            # on the Filtered Out dashboard page so the user can spot jobs
            # the keyword matcher dismissed but that might still be relevant).
            above = ks["score"] >= threshold
            initial_status = "new" if above else "filtered_out"
            inserted = db_store.insert_if_new(conn, full, initial_status=initial_status)
            if inserted:
                if above:
                    stats.inserted += 1
                else:
                    stats.inserted_filtered_out += 1
            else:
                # Tiny race window — another writer added this id between the
                # earlier get_job check and now. Treat as skip-existing.
                stats.skipped_existing += 1
    finally:
        conn.close()

    stats.elapsed_seconds = (datetime.now() - started).total_seconds()
    progress("done", stats.as_dict())
    return stats


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--keywords",
                   help="defaults to the DB-stored preference if omitted")
    p.add_argument("--location",
                   help="free-text location; ignored if --location-geo-id given")
    p.add_argument("--location-geo-id",
                   help="LinkedIn geoId (skips typeahead resolve)")
    p.add_argument("--days", type=int, default=DEFAULT_DAYS_BACK,
                   help=f"how many days back to scan (default {DEFAULT_DAYS_BACK})")
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                   help=f"keyword similarity threshold for inclusion (default {DEFAULT_THRESHOLD})")
    p.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS,
                   help=f"safety cap on results (default {DEFAULT_MAX_RESULTS})")
    p.add_argument("--profile", default="profile/profile.md")
    p.add_argument("--db", default=str(db_store.DEFAULT_DB_PATH))
    args = p.parse_args()

    # Fill in keywords/location from stored preferences when not given on CLI.
    conn = db_store.init_db(Path(args.db))
    try:
        prefs = db_store.get_preferences(conn)
    finally:
        conn.close()

    keywords = args.keywords or prefs.get("keywords")
    location = args.location or prefs.get("location")
    geo_id = args.location_geo_id or prefs.get("location_geo_id")
    if not keywords:
        p.error("no keywords provided and no DB preference set")

    def on_progress(phase: str, payload: dict) -> None:
        if phase == "scoring" and payload["current"] % 5 != 0:
            return  # quieter logging on CLI
        print(f"  [{phase}] {payload}")

    logging.basicConfig(level=logging.WARNING)
    stats = run_backfill(
        keywords=keywords,
        location=location,
        location_geo_id=geo_id,
        days_back=args.days,
        threshold=args.threshold,
        max_results=args.max_results,
        db_path=Path(args.db),
        profile_path=Path(args.profile),
        on_progress=on_progress,
    )
    print(f"\nBackfill complete: {json.dumps(stats.as_dict(), indent=2)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
