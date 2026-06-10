from pathlib import Path
from tools.linkedin.get_job_details import parse_detail_html

FIXTURE = Path(__file__).parent / "fixtures/linkedin_job_detail_4417627058.html"

def test_parse_detail_has_description():
    d = parse_detail_html(FIXTURE.read_text())
    assert d["description"], "expected non-empty description"
    assert len(d["description"]) > 200

def test_parse_detail_extracts_criteria():
    d = parse_detail_html(FIXTURE.read_text())
    assert d.get("seniority")
    assert d.get("employment_type")
    assert d.get("job_function")
    assert d.get("industry")

def test_parse_detail_extracts_company_and_location():
    d = parse_detail_html(FIXTURE.read_text())
    assert d.get("company")
    assert d.get("location")
