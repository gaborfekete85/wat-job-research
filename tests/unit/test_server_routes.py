"""Tests for tools/server/app.py — FastAPI routes against an in-memory test DB."""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tools.db import store as db_store
from tools.server import app as server_app
from tools.server import pdf_jobs


@pytest.fixture()
def test_app(tmp_path):
    db_path = tmp_path / "jobs.db"
    pdf_jobs._state.clear()
    app = server_app.create_app(db_path=db_path)
    with TestClient(app) as client:
        yield client, db_path


def _seed(db_path, **overrides):
    conn = db_store.init_db(db_path)
    job = {
        "job_id": "100",
        "title": "Senior Eng",
        "company": "Acme",
        "location": "Zurich",
        "url": "https://x/y",
        "apply_url": "https://x/apply",
        "description": "Senior engineer wanted.",
        "keyword_score": {"score": 0.6, "matched": ["AWS"], "missing": []},
    }
    job.update(overrides)
    db_store.upsert_job(conn, job)
    conn.close()


def test_list_jobs_empty(test_app):
    client, _ = test_app
    r = client.get("/api/jobs")
    assert r.status_code == 200
    body = r.json()
    assert body == {"new": [], "viewed": [], "staged": [], "submitted": []}


def test_list_jobs_returns_new_jobs(test_app):
    client, db_path = test_app
    _seed(db_path)
    body = client.get("/api/jobs").json()
    assert len(body["new"]) == 1
    assert body["new"][0]["id"] == "100"
    assert body["new"][0]["has_match_result"] is False
    assert body["viewed"] == []


def test_view_transitions_new_to_viewed(test_app):
    client, db_path = test_app
    _seed(db_path)
    r = client.post("/api/jobs/100/view")
    assert r.status_code == 200
    assert r.json()["status"] == "viewed"

    body = client.get("/api/jobs").json()
    assert body["new"] == []
    assert len(body["viewed"]) == 1


def test_view_idempotent_when_already_viewed(test_app):
    client, db_path = test_app
    _seed(db_path)
    client.post("/api/jobs/100/view")
    r = client.post("/api/jobs/100/view")
    assert r.status_code == 200
    assert r.json()["status"] == "viewed"


def test_dismiss_moves_out_of_lists(test_app):
    client, db_path = test_app
    _seed(db_path)
    r = client.post("/api/jobs/100/dismiss")
    assert r.status_code == 200
    body = client.get("/api/jobs").json()
    assert body["new"] == [] and body["viewed"] == []


# ── Generic status endpoint (drag-and-drop) ─────────────────────────────────


def test_set_status_moves_between_columns(test_app):
    client, db_path = test_app
    _seed(db_path)

    # NEW → SUBMITTED (skip intermediate states is allowed — user is dragging)
    r = client.post("/api/jobs/100/status", json={"status": "submitted"})
    assert r.status_code == 200
    assert r.json()["status"] == "submitted"

    body = client.get("/api/jobs").json()
    assert body["new"] == []
    assert len(body["submitted"]) == 1

    # SUBMITTED → VIEWED (going backwards is fine)
    r = client.post("/api/jobs/100/status", json={"status": "viewed"})
    assert r.status_code == 200
    body = client.get("/api/jobs").json()
    assert len(body["viewed"]) == 1
    assert body["submitted"] == []


def test_set_status_validates_target(test_app):
    client, db_path = test_app
    _seed(db_path)
    r = client.post("/api/jobs/100/status", json={"status": "bogus"})
    assert r.status_code == 400


def test_set_status_requires_status_field(test_app):
    client, db_path = test_app
    _seed(db_path)
    r = client.post("/api/jobs/100/status", json={})
    assert r.status_code == 400


def test_set_status_404_when_missing(test_app):
    client, _ = test_app
    r = client.post("/api/jobs/nope/status", json={"status": "viewed"})
    assert r.status_code == 404


def test_get_job_includes_match_result(test_app):
    client, db_path = test_app
    _seed(db_path, llm_score={
        "final_score": 0.81,
        "skills_match": 0.9,
        "seniority_fit": "fit",
        "matched_skills": ["AWS"],
        "missing_critical": [],
        "reasoning": "good",
        "suggested_emphasis": {"tailored_summary": "s"},
    })
    r = client.get("/api/jobs/100")
    assert r.status_code == 200
    body = r.json()
    assert body["llm_final_score"] == 0.81
    assert body["match_result"]["seniority_fit"] == "fit"


def test_generate_pdf_refuses_when_no_match_result(test_app):
    client, db_path = test_app
    _seed(db_path)  # no llm_score → no match_result_json
    r = client.post("/api/jobs/100/generate-pdf")
    assert r.status_code == 409
    assert "needs_llm_scoring" in r.text


def test_generate_pdf_kicks_off_background_when_match_present(test_app, monkeypatch):
    client, db_path = test_app
    _seed(db_path, llm_score={"final_score": 0.81, "reasoning": "ok"})

    calls = []

    def fake_pipeline(job_id, *, db_path, profile_path, resources_dir):
        calls.append(job_id)
        pdf_jobs.set_state(job_id, "done")
        return Path("/tmp/fake.pdf")

    monkeypatch.setattr(pdf_jobs, "run_pdf_pipeline", fake_pipeline)

    r = client.post("/api/jobs/100/generate-pdf")
    assert r.status_code == 202
    assert r.json()["state"] == "running"
    # Background task ran inline in TestClient — check the call happened
    assert calls == ["100"]

    status = client.get("/api/jobs/100/pdf-status").json()
    assert status["state"] == "done"


def test_pdf_status_returns_idle_for_unknown_job(test_app):
    client, _ = test_app
    r = client.get("/api/jobs/999/pdf-status")
    assert r.status_code == 200
    assert r.json()["state"] == "idle"


def test_get_job_404_when_missing(test_app):
    client, _ = test_app
    r = client.get("/api/jobs/nope")
    assert r.status_code == 404


def test_pdfs_endpoint_404_when_no_path(test_app):
    client, db_path = test_app
    _seed(db_path)
    r = client.get("/pdfs/100.pdf")
    assert r.status_code == 404


# ── Preferences ──────────────────────────────────────────────────────────────


def test_get_preferences_returns_defaults(test_app):
    client, _ = test_app
    r = client.get("/api/preferences")
    assert r.status_code == 200
    body = r.json()
    assert "keywords" in body
    assert "location" in body
    assert body["location"] == "Zurich, Switzerland"


def test_put_preferences_updates_and_persists(test_app):
    client, _ = test_app
    r = client.put("/api/preferences", json={"location": "Geneva, Switzerland"})
    assert r.status_code == 200
    assert r.json()["location"] == "Geneva, Switzerland"

    # Round-trip via GET
    r = client.get("/api/preferences")
    assert r.json()["location"] == "Geneva, Switzerland"


def test_put_preferences_rejects_unknown_key(test_app):
    client, _ = test_app
    r = client.put("/api/preferences", json={"not_a_real_key": "x"})
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["error"] == "invalid_preferences"
    assert "not_a_real_key" in body["detail"]["fields"]


def test_put_preferences_rejects_empty_value(test_app):
    client, _ = test_app
    r = client.put("/api/preferences", json={"keywords": "   "})
    assert r.status_code == 400


def test_put_preferences_clears_location_geo_id_with_null(test_app):
    client, _ = test_app
    client.put("/api/preferences", json={"location_geo_id": "107814425"})
    assert client.get("/api/preferences").json()["location_geo_id"] == "107814425"

    # Now clear it
    r = client.put("/api/preferences", json={"location_geo_id": None})
    assert r.status_code == 200
    assert "location_geo_id" not in r.json()


# ── Location typeahead ──────────────────────────────────────────────────────


def test_location_typeahead_returns_resolved_hits(test_app, monkeypatch):
    from tools.server import app as server_app
    monkeypatch.setattr(server_app.resolve_location, "resolve", lambda q: [
        {"id": "107814425", "displayName": "Zurich, Zurich, Switzerland"},
        {"id": "102799079", "displayName": "Zurich, Ontario, Canada"},
    ])
    client, _ = test_app
    r = client.get("/api/locations/typeahead?q=Zurich")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["id"] == "107814425"


def test_location_typeahead_empty_for_short_query(test_app):
    client, _ = test_app
    r = client.get("/api/locations/typeahead?q=Z")
    assert r.status_code == 200
    assert r.json() == []


def test_location_typeahead_502_on_upstream_failure(test_app, monkeypatch):
    from tools.server import app as server_app

    def boom(q):
        raise RuntimeError("LinkedIn rate-limited")
    monkeypatch.setattr(server_app.resolve_location, "resolve", boom)

    client, _ = test_app
    r = client.get("/api/locations/typeahead?q=Zurich")
    assert r.status_code == 502
