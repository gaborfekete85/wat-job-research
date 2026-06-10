import csv, json
from pathlib import Path
from tools.application.stage import stage_application
from tools.application.mark_submitted import mark_submitted

def test_mark_submitted_writes_marker_and_updates_csv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    job = {"job_id": "999", "title": "Eng", "company": "Acme",
           "url": "https://x", "apply_url": "https://x/apply"}
    cv = tmp_path / "cv.pdf"; cv.write_bytes(b"%PDF")
    folder = Path(stage_application(job, cv_pdf=cv))
    res = mark_submitted("999", notes="Applied via Easy Apply")
    assert res == str(folder)
    marker = folder / "submitted.json"
    assert marker.exists()
    data = json.loads(marker.read_text())
    assert data["notes"] == "Applied via Easy Apply"
    rows = list(csv.reader(Path("temp/outputs/applications/applications.csv").read_text().splitlines()))
    assert rows[1][3] == "submitted"
    assert rows[1][5]  # submitted_at column set

def test_mark_submitted_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    job = {"job_id": "999", "title": "Eng", "company": "Acme",
           "url": "https://x", "apply_url": "https://x/apply"}
    cv = tmp_path / "cv.pdf"; cv.write_bytes(b"%PDF")
    stage_application(job, cv_pdf=cv)
    mark_submitted("999")
    # Second call should raise
    import pytest
    with pytest.raises(RuntimeError):
        mark_submitted("999")
