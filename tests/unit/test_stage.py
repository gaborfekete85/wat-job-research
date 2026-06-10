import csv, json
from pathlib import Path
from tools.application.stage import stage_application

def test_stage_creates_folder_with_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    job = {"job_id": "1234", "title": "Sr Eng", "company": "Acme!Co",
           "url": "https://example.com/x", "apply_url": "https://example.com/apply"}
    cv = tmp_path / "cv.pdf"; cv.write_bytes(b"%PDF-1.4 ...")
    out_dir = stage_application(job, cv_pdf=cv)
    assert Path(out_dir).is_dir()
    assert (Path(out_dir) / "tailored_cv.pdf").exists()
    assert (Path(out_dir) / "job_details.json").exists()
    assert (Path(out_dir) / "apply_url.txt").read_text().strip() == job["apply_url"]
    # CSV master log
    csv_path = Path("temp/outputs/applications/applications.csv")
    assert csv_path.exists()
    rows = list(csv.reader(csv_path.read_text().splitlines()))
    assert rows[0] == ["job_id", "company", "title", "status", "staged_at", "submitted_at", "folder"]
    assert rows[1][0] == "1234"
    assert rows[1][3] == "staged"
