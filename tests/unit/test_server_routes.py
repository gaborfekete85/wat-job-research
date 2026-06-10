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
