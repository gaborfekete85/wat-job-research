"""Tests for tools/db/store.py — sqlite-backed jobs table."""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from tools.db import store


@pytest.fixture()
def db(tmp_path):
    conn = store.init_db(tmp_path / "jobs.db")
    yield conn
    conn.close()


def _sample_job(**overrides):
    job = {
        "job_id": "1234",
        "title": "Senior Eng",
        "company": "Acme",
        "location": "Zurich",
        "url": "https://x/y",
        "description": "We need a senior engineer.",
        "apply_url": "https://x/apply",
        "keyword_score": {"score": 0.6, "matched": ["AWS"], "missing": ["Rust"], "jd_skills": ["AWS", "Rust"]},
    }
    job.update(overrides)
    return job


def test_upsert_creates_row_with_status_new(db):
    store.upsert_job(db, _sample_job())
    row = store.get_job(db, "1234")
    assert row is not None
    assert row["status"] == "new"
    assert row["title"] == "Senior Eng"
    assert row["keyword_score"] == 0.6
    assert row["llm_final_score"] is None
    assert row["match_result_json"] is None
    assert row["tailored_pdf_path"] is None
    assert row["discovered_at"]
    assert row["viewed_at"] is None


def test_upsert_is_idempotent_on_same_id(db):
    store.upsert_job(db, _sample_job())
    discovered_at = store.get_job(db, "1234")["discovered_at"]

    # Modify and re-upsert
    store.upsert_job(db, _sample_job(title="Senior Eng II"))
    row = store.get_job(db, "1234")

    # No duplicate, content updated, discovered_at preserved
    all_rows = store.list_jobs(db)
    assert len(all_rows) == 1
    assert row["title"] == "Senior Eng II"
    assert row["discovered_at"] == discovered_at


def test_upsert_preserves_status_on_update(db):
    store.upsert_job(db, _sample_job())
    store.set_status(db, "1234", "viewed")
    assert store.get_job(db, "1234")["status"] == "viewed"

    # Re-ingest the same job — status must NOT flip back to 'new'
    store.upsert_job(db, _sample_job(title="Senior Eng II"))
    row = store.get_job(db, "1234")
    assert row["status"] == "viewed"
    assert row["title"] == "Senior Eng II"


def test_upsert_attaches_llm_score_when_present(db):
    job = _sample_job()
    job["llm_score"] = {
        "final_score": 0.82,
        "skills_match": 0.9,
        "seniority_fit": "fit",
        "matched_skills": ["AWS"],
        "missing_critical": [],
        "reasoning": "Strong match.",
        "suggested_emphasis": {"tailored_summary": "..."},
    }
    store.upsert_job(db, job)
    row = store.get_job(db, "1234")
    assert row["llm_final_score"] == 0.82
    parsed = json.loads(row["match_result_json"])
    assert parsed["seniority_fit"] == "fit"


def test_upsert_does_not_clobber_llm_score_with_null(db):
    job = _sample_job()
    job["llm_score"] = {"final_score": 0.82, "reasoning": "ok"}
    store.upsert_job(db, job)
    assert store.get_job(db, "1234")["llm_final_score"] == 0.82

    # Re-upsert WITHOUT an llm_score — must keep the existing one
    store.upsert_job(db, _sample_job())
    assert store.get_job(db, "1234")["llm_final_score"] == 0.82


def test_set_status_validates_value(db):
    store.upsert_job(db, _sample_job())
    with pytest.raises(ValueError):
        store.set_status(db, "1234", "bogus")


def test_set_status_stamps_timestamps(db):
    store.upsert_job(db, _sample_job())
    store.set_status(db, "1234", "viewed")
    row = store.get_job(db, "1234")
    assert row["viewed_at"]
    assert row["staged_at"] is None

    store.set_status(db, "1234", "staged")
    row = store.get_job(db, "1234")
    assert row["staged_at"]


def test_set_status_does_not_reset_existing_timestamp(db):
    store.upsert_job(db, _sample_job())
    store.set_status(db, "1234", "viewed")
    first_viewed_at = store.get_job(db, "1234")["viewed_at"]

    # Re-set to viewed — viewed_at must stay at the original timestamp
    store.set_status(db, "1234", "viewed")
    assert store.get_job(db, "1234")["viewed_at"] == first_viewed_at


def test_list_jobs_filters_by_status(db):
    store.upsert_job(db, _sample_job(job_id="1"))
    store.upsert_job(db, _sample_job(job_id="2"))
    store.upsert_job(db, _sample_job(job_id="3"))
    store.set_status(db, "2", "viewed")

    assert {j["id"] for j in store.list_jobs(db, status="new")} == {"1", "3"}
    assert {j["id"] for j in store.list_jobs(db, status="viewed")} == {"2"}
    assert len(store.list_jobs(db)) == 3


def test_insert_if_new_returns_true_when_new(db):
    inserted = store.insert_if_new(db, _sample_job())
    assert inserted is True
    assert store.get_job(db, "1234") is not None


def test_insert_if_new_returns_false_when_exists(db):
    store.upsert_job(db, _sample_job())
    inserted = store.insert_if_new(db, _sample_job(title="changed"))
    assert inserted is False
    # Existing row UNTOUCHED — content not refreshed
    assert store.get_job(db, "1234")["title"] == "Senior Eng"


def test_insert_if_new_preserves_status(db):
    store.upsert_job(db, _sample_job())
    store.set_status(db, "1234", "viewed")
    store.insert_if_new(db, _sample_job(title="changed"))
    assert store.get_job(db, "1234")["status"] == "viewed"


def test_insert_if_new_accepts_initial_status(db):
    inserted = store.insert_if_new(db, _sample_job(), initial_status="filtered_out")
    assert inserted is True
    assert store.get_job(db, "1234")["status"] == "filtered_out"


def test_insert_if_new_rejects_invalid_initial_status(db):
    with pytest.raises(ValueError, match="invalid initial_status"):
        store.insert_if_new(db, _sample_job(), initial_status="bogus")


def test_set_status_accepts_filtered_out(db):
    store.upsert_job(db, _sample_job())
    store.set_status(db, "1234", "filtered_out")
    assert store.get_job(db, "1234")["status"] == "filtered_out"


def test_set_tailored_pdf(db, tmp_path):
    store.upsert_job(db, _sample_job())
    pdf = tmp_path / "tailored.pdf"
    pdf.write_bytes(b"%PDF")
    store.set_tailored_pdf(db, "1234", pdf)
    assert store.get_job(db, "1234")["tailored_pdf_path"] == str(pdf)


# ── Preferences ──────────────────────────────────────────────────────────────


def test_get_preferences_returns_defaults_when_empty(db):
    prefs = store.get_preferences(db)
    assert prefs["keywords"] == store.DEFAULT_PREFERENCES["keywords"]
    assert prefs["location"] == store.DEFAULT_PREFERENCES["location"]


def test_set_preference_overrides_default(db):
    store.set_preference(db, "location", "Geneva, Switzerland")
    prefs = store.get_preferences(db)
    assert prefs["location"] == "Geneva, Switzerland"
    # Other keys still come from defaults
    assert prefs["keywords"] == store.DEFAULT_PREFERENCES["keywords"]


def test_set_preference_is_idempotent_upsert(db):
    store.set_preference(db, "location", "Geneva, Switzerland")
    store.set_preference(db, "location", "Lausanne, Switzerland")
    prefs = store.get_preferences(db)
    assert prefs["location"] == "Lausanne, Switzerland"


def test_set_preference_rejects_unknown_key(db):
    with pytest.raises(ValueError, match="unknown preference"):
        store.set_preference(db, "made_up_key", "value")


def test_set_preference_rejects_empty_value(db):
    with pytest.raises(ValueError, match="non-empty"):
        store.set_preference(db, "keywords", "   ")


def test_set_preference_trims_whitespace(db):
    store.set_preference(db, "keywords", "  ai OR consultant  ")
    assert store.get_preferences(db)["keywords"] == "ai OR consultant"


def test_location_geo_id_is_optional_and_storable(db):
    # No default for location_geo_id — absent from defaults
    assert "location_geo_id" not in store.get_preferences(db)
    store.set_preference(db, "location_geo_id", "107814425")
    assert store.get_preferences(db)["location_geo_id"] == "107814425"


def test_location_geo_id_clearable_with_none(db):
    store.set_preference(db, "location_geo_id", "107814425")
    store.set_preference(db, "location_geo_id", None)
    assert "location_geo_id" not in store.get_preferences(db)


def test_location_geo_id_clearable_with_empty_string(db):
    store.set_preference(db, "location_geo_id", "107814425")
    store.set_preference(db, "location_geo_id", "")
    assert "location_geo_id" not in store.get_preferences(db)


def test_defaultable_key_cannot_be_cleared(db):
    # Clearing 'keywords' or 'location' would surprise the user by silently
    # reverting to defaults — disallow that path.
    with pytest.raises(ValueError, match="non-empty"):
        store.set_preference(db, "keywords", None)
    with pytest.raises(ValueError, match="non-empty"):
        store.set_preference(db, "location", "")
