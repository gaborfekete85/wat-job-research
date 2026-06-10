"""Tests for tools/workflow/search.py — the backfill orchestrator."""
from __future__ import annotations
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.db import store as db_store
from tools.workflow import search as backfill


# ── Test fixtures ────────────────────────────────────────────────────────────


@pytest.fixture()
def isolated_db(tmp_path):
    db_path = tmp_path / "jobs.db"
    conn = db_store.init_db(db_path)
    conn.close()
    yield db_path


@pytest.fixture()
def fake_profile(tmp_path):
    p = tmp_path / "profile.md"
    p.write_text("""---
name: Test
title: Engineer
email: t@e.st
phone: "+1"
location: Zurich
summary: A test profile.
skills:
  languages: [Python]
  frameworks: [Spring, Kafka]
  cloud_devops: [AWS, Kubernetes]
---
body
""")
    return p


def _summary(job_id: str, **overrides):
    s = {
        "job_id": job_id,
        "title": f"Senior Engineer {job_id}",
        "company": f"Co {job_id}",
        "location": "Zurich",
        "url": f"https://x/{job_id}",
        "posted": "2026-06-10",
    }
    s.update(overrides)
    return s


def _detail(job_id: str, description: str):
    return {
        "title": f"Senior Engineer {job_id}",
        "company": f"Co {job_id}",
        "location": "Zurich",
        "description": description,
        "seniority": "Mid-Senior",
        "employment_type": "Full-time",
        "job_function": "Eng",
        "industry": "Software",
        "apply_url": f"https://x/{job_id}/apply",
    }


# ── Tests ────────────────────────────────────────────────────────────────────


def test_backfill_inserts_jobs_above_threshold(isolated_db, fake_profile):
    summaries = [_summary("A"), _summary("B")]
    details = {
        # 4 skills, all in profile → score 1.0 (well above 0.7)
        "A": _detail("A", "We need AWS, Kubernetes, Kafka, Python."),
        # Only 1 of 3 skills in profile → score 0.33 (below 0.7)
        "B": _detail("B", "We need Rust, Go, Python."),
    }

    with patch("tools.workflow.search.search_jobs.search", return_value=summaries), \
         patch("tools.workflow.search._fetch_job_detail", side_effect=lambda jid: details[jid]):
        stats = backfill.run_backfill(
            keywords="engineer",
            location_geo_id="107814425",
            days_back=4, threshold=0.7,
            db_path=isolated_db, profile_path=fake_profile,
        )

    assert stats.total_found == 2
    assert stats.inserted == 1
    assert stats.skipped_below_threshold == 1
    assert stats.skipped_existing == 0

    conn = db_store.init_db(isolated_db)
    try:
        assert db_store.get_job(conn, "A") is not None
        assert db_store.get_job(conn, "B") is None
    finally:
        conn.close()


def test_backfill_skips_already_existing_jobs(isolated_db, fake_profile):
    # Pre-populate A with status=viewed; backfill must NOT clobber it.
    conn = db_store.init_db(isolated_db)
    try:
        db_store.upsert_job(conn, {
            "job_id": "A", "title": "Original", "company": "Original",
            "url": "https://x/A", "description": "old", "apply_url": "https://x/A/apply",
        })
        db_store.set_status(conn, "A", "viewed")
    finally:
        conn.close()

    summaries = [_summary("A"), _summary("C")]
    details = {
        "A": _detail("A", "We need AWS, Kubernetes, Kafka, Python."),
        "C": _detail("C", "We need AWS, Kubernetes, Kafka, Python."),
    }
    with patch("tools.workflow.search.search_jobs.search", return_value=summaries), \
         patch("tools.workflow.search._fetch_job_detail", side_effect=lambda jid: details[jid]):
        stats = backfill.run_backfill(
            keywords="engineer", location_geo_id="X",
            days_back=4, threshold=0.7,
            db_path=isolated_db, profile_path=fake_profile,
        )

    assert stats.inserted == 1
    assert stats.skipped_existing == 1

    conn = db_store.init_db(isolated_db)
    try:
        row_a = db_store.get_job(conn, "A")
        # PRE-EXISTING row untouched: title still "Original", status still 'viewed'
        assert row_a["title"] == "Original"
        assert row_a["status"] == "viewed"
        # New row C added
        assert db_store.get_job(conn, "C") is not None
    finally:
        conn.close()


def test_backfill_uses_location_geo_id_when_provided(isolated_db, fake_profile):
    """When location_geo_id is given, we MUST skip resolve_location."""
    with patch("tools.workflow.search.search_jobs.search", return_value=[]) as mock_search, \
         patch("tools.workflow.search.resolve_location.resolve") as mock_resolve:
        backfill.run_backfill(
            keywords="engineer",
            location_geo_id="107814425",   # supplied → resolve not called
            db_path=isolated_db, profile_path=fake_profile,
        )
    mock_resolve.assert_not_called()
    args, kwargs = mock_search.call_args
    # search receives the geo_id
    assert args[1] == "107814425" or kwargs.get("geo_id") == "107814425"


def test_backfill_resolves_when_only_location_string_given(isolated_db, fake_profile):
    with patch("tools.workflow.search.resolve_location.resolve",
               return_value=[{"id": "999", "displayName": "Test, Switzerland"}]) as mock_resolve, \
         patch("tools.workflow.search.search_jobs.search", return_value=[]):
        backfill.run_backfill(
            keywords="engineer", location="Test", db_path=isolated_db, profile_path=fake_profile,
        )
    mock_resolve.assert_called_once_with("Test")


def test_backfill_requires_keywords_or_geo(isolated_db, fake_profile):
    with pytest.raises(ValueError, match="location"):
        backfill.run_backfill(
            keywords="engineer", db_path=isolated_db, profile_path=fake_profile,
        )


def test_backfill_calls_progress_callback(isolated_db, fake_profile):
    summaries = [_summary("X")]
    details = {"X": _detail("X", "We need Python AWS Kafka.")}
    phases = []

    def progress(phase, payload):
        phases.append(phase)

    with patch("tools.workflow.search.search_jobs.search", return_value=summaries), \
         patch("tools.workflow.search._fetch_job_detail", side_effect=lambda jid: details[jid]):
        backfill.run_backfill(
            keywords="engineer", location_geo_id="X",
            db_path=isolated_db, profile_path=fake_profile,
            on_progress=progress,
        )

    assert "resolving" in phases
    assert "searching" in phases
    assert "scoring" in phases
    assert phases[-1] == "done"


def test_backfill_continues_on_individual_fetch_failures(isolated_db, fake_profile):
    """One bad job_id shouldn't kill the whole batch."""
    summaries = [_summary("OK"), _summary("BAD"), _summary("OK2")]

    def fetcher(jid):
        if jid == "BAD":
            raise RuntimeError("LinkedIn 500")
        return _detail(jid, "We need Python AWS Kafka.")

    with patch("tools.workflow.search.search_jobs.search", return_value=summaries), \
         patch("tools.workflow.search._fetch_job_detail", side_effect=fetcher):
        stats = backfill.run_backfill(
            keywords="engineer", location_geo_id="X",
            db_path=isolated_db, profile_path=fake_profile,
        )

    assert stats.inserted == 2
    assert stats.fetch_failures == 1
