from pathlib import Path
from tools.linkedin.search_jobs import parse_search_html

FIXTURE = Path(__file__).parent / "fixtures/linkedin_search_zurich.html"

def test_parse_search_returns_jobs():
    jobs = parse_search_html(FIXTURE.read_text())
    assert len(jobs) >= 1

def test_parsed_job_has_required_fields():
    jobs = parse_search_html(FIXTURE.read_text())
    j = jobs[0]
    assert j["job_id"].isdigit()
    assert j["title"]
    assert j["company"]
    assert j["location"]
    assert j["url"].startswith("http")

def test_parsed_job_includes_posted_date_when_present():
    jobs = parse_search_html(FIXTURE.read_text())
    # Most cards have a <time datetime="..."> — at least one of ours should
    assert any(j.get("posted") for j in jobs)
