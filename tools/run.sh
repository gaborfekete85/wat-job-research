#!/usr/bin/env bash
# End-to-end job-search pipeline. See workflows/find-and-apply-jobs.md for the same
# steps in Mode-C agent-readable form.
set -euo pipefail

# Resolve project root (the directory containing this script's parent)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"
PYTHON="$PROJECT_ROOT/.venv/bin/python"

# Defaults
LOCATION=""
KEYWORDS=""
FILTER_CUTOFF="0.4"
ACCEPT_THRESHOLD="0.7"
POSTED_WITHIN_HOURS=""
LIMIT="50"
WITH_COVER_LETTER=0
WITH_ATS_ANSWERS=0
NO_CACHE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --location) LOCATION="$2"; shift 2 ;;
    --keywords) KEYWORDS="$2"; shift 2 ;;
    --filter-cutoff) FILTER_CUTOFF="$2"; shift 2 ;;
    --accept-threshold) ACCEPT_THRESHOLD="$2"; shift 2 ;;
    --posted-within-hours) POSTED_WITHIN_HOURS="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
    --with-cover-letter) WITH_COVER_LETTER=1; shift ;;
    --with-ats-answers)  WITH_ATS_ANSWERS=1; shift ;;
    --no-cache) NO_CACHE=1; shift ;;
    *) echo "unknown flag: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$LOCATION" ]] && { echo "--location required" >&2; exit 1; }
[[ -z "$KEYWORDS" ]] && { echo "--keywords required" >&2; exit 1; }

# Load .env if present
[[ -f .env ]] && set -a && source .env && set +a
[[ -z "${ANTHROPIC_API_KEY:-}" ]] && { echo "ANTHROPIC_API_KEY missing" >&2; exit 1; }
[[ ! -f temp/resources/profile.md ]] && { echo "temp/resources/profile.md missing" >&2; exit 1; }

TS=$(date -u +"%Y-%m-%dT%H-%M")
RUN_DIR="temp/outputs/runs/$TS"
CACHE_DIR="temp/outputs/cache"
mkdir -p "$RUN_DIR" "$CACHE_DIR"
LOG="$RUN_DIR/run.log"
exec > >(tee -a "$LOG") 2>&1

echo "[0/7] resolve_location: $LOCATION"
GEO_HIT=$("$PYTHON" -m tools.linkedin.resolve_location "$LOCATION" --pick-first)
GEO_ID=$("$PYTHON" -c "import json,sys; print(json.loads(sys.stdin.read())['id'])" <<< "$GEO_HIT")
echo "  → geoId=$GEO_ID"

echo "[1/7] search_jobs"
SEARCH_ARGS=(--keywords "$KEYWORDS" --geo-id "$GEO_ID" --limit "$LIMIT")
[[ -n "$POSTED_WITHIN_HOURS" ]] && SEARCH_ARGS+=(--posted-within-hours "$POSTED_WITHIN_HOURS")
"$PYTHON" -m tools.linkedin.search_jobs "${SEARCH_ARGS[@]}" -o "$RUN_DIR/jobs_raw.json"
TOTAL=$("$PYTHON" -c "import json; print(len(json.load(open('$RUN_DIR/jobs_raw.json'))))")
echo "  → $TOTAL jobs"

echo "[1.5/7] fetch details (cache-aware)"
"$PYTHON" <<PY
import json, os, time
from pathlib import Path
from datetime import datetime, timezone
import subprocess, sys
jobs = json.load(open("$RUN_DIR/jobs_raw.json"))
cache_dir = Path("$CACHE_DIR")
profile_mtime = os.path.getmtime("temp/resources/profile.md")
NO_CACHE = bool(int("$NO_CACHE"))
out = []
for j in jobs:
    jid = j["job_id"]
    cache = cache_dir / f"{jid}.json"
    detail = None
    if cache.exists() and not NO_CACHE:
        d = json.loads(cache.read_text())
        if d.get("job_detail"):
            detail = d["job_detail"]
    if detail is None:
        r = subprocess.run([sys.executable, "-m", "tools.linkedin.get_job_details", jid],
                           capture_output=True, text=True, check=True)
        detail = json.loads(r.stdout)
        cache.write_text(json.dumps({"job_detail": detail,
                                      "cached_at": datetime.now(timezone.utc).isoformat()}, indent=2))
    merged = {**j, **detail}
    out.append(merged)
Path("$RUN_DIR/jobs_with_details.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
PY

echo "[2/7] keyword pre-filter (cutoff $FILTER_CUTOFF)"
"$PYTHON" <<PY
import json, sys
from pathlib import Path
from tools.match.extract_skills import extract_from_text, extract_from_profile_yaml
from tools.match.score_keyword import score
profile = Path("temp/resources/profile.md").read_text()
profile_skills = extract_from_profile_yaml(profile)
cutoff = float("$FILTER_CUTOFF")
jobs = json.load(open("$RUN_DIR/jobs_with_details.json"))
out = []
for j in jobs:
    jd_skills = extract_from_text(j.get("description") or "")
    s = score(profile_skills, jd_skills)
    j["keyword_score"] = s
    if s["score"] >= cutoff:
        out.append(j)
Path("$RUN_DIR/jobs_filtered.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
print(f"  → {len(out)}/{len(jobs)} passed filter")
PY

echo "[3/7] LLM scoring (cost ≈ \$0.01/job)"
"$PYTHON" <<PY
import json, os, subprocess, sys, tempfile
from pathlib import Path
from datetime import datetime, timezone
NO_CACHE = bool(int("$NO_CACHE"))
profile_mtime = os.path.getmtime("temp/resources/profile.md")
cache_dir = Path("$CACHE_DIR")
jobs = json.load(open("$RUN_DIR/jobs_filtered.json"))
out = []
for j in jobs:
    jid = j["job_id"]
    cache = cache_dir / f"{jid}.json"
    cached = json.loads(cache.read_text()) if cache.exists() else {}
    llm = cached.get("llm_score")
    cached_at = cached.get("cached_at")
    if llm and (cached_at and datetime.fromisoformat(cached_at).timestamp() < profile_mtime):
        llm = None
    if NO_CACHE: llm = None
    if llm is None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as jf, \
             tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as kf:
            json.dump(j, jf); jf.flush()
            json.dump(j["keyword_score"], kf); kf.flush()
            r = subprocess.run([sys.executable, "-m", "tools.match.score_llm",
                                "--profile", "temp/resources/profile.md",
                                "--job-details", jf.name,
                                "--keyword-result", kf.name],
                               capture_output=True, text=True, check=True)
            llm = json.loads(r.stdout)
        cache.write_text(json.dumps({**cached, "llm_score": llm,
                                      "cached_at": datetime.now(timezone.utc).isoformat()}, indent=2))
    j["llm_score"] = llm
    out.append(j)
Path("$RUN_DIR/jobs_matched.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
PY

echo "[4-6/7] tailor → render → stage (accept threshold $ACCEPT_THRESHOLD)"
"$PYTHON" <<PY
import json, subprocess, sys, tempfile
from pathlib import Path
ACCEPT = float("$ACCEPT_THRESHOLD")
WITH_COVER = bool(int("$WITH_COVER_LETTER"))
WITH_ATS = bool(int("$WITH_ATS_ANSWERS"))
jobs = json.load(open("$RUN_DIR/jobs_matched.json"))
accepted = [j for j in jobs if (j["llm_score"]["final_score"] >= ACCEPT)]
staged_count = 0
for j in accepted:
    jid = j["job_id"]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            jd_path = tmp / "job.json"; jd_path.write_text(json.dumps(j))
            match_path = tmp / "match.json"; match_path.write_text(json.dumps(j["llm_score"]))
            yml_path = tmp / "tailored.yml"
            subprocess.run([sys.executable, "-m", "tools.cv.tailor",
                            "--profile", "temp/resources/profile.md",
                            "--match-result", str(match_path),
                            "-o", str(yml_path)], check=True)
            pdf_path = tmp / "tailored_cv.pdf"
            subprocess.run([sys.executable, "-m", "tools.cv.render", str(yml_path), "-o", str(pdf_path)], check=True)
            extra = []
            if WITH_COVER:
                cl = tmp / "cover_letter.md"
                subprocess.run([sys.executable, "-m", "tools.application.draft_cover_letter",
                                "--profile", "temp/resources/profile.md",
                                "--job-details", str(jd_path),
                                "--match-result", str(match_path),
                                "-o", str(cl)], check=True)
                extra += ["--cover-letter", str(cl)]
            if WITH_ATS:
                ats = tmp / "ats_answers.md"
                subprocess.run([sys.executable, "-m", "tools.application.draft_ats_answers",
                                "--profile", "temp/resources/profile.md",
                                "--job-details", str(jd_path),
                                "-o", str(ats)], check=True)
                extra += ["--ats-answers", str(ats)]
            subprocess.run([sys.executable, "-m", "tools.application.stage",
                            "--job-details", str(jd_path),
                            "--cv", str(pdf_path),
                            "--match-result", str(match_path),
                            *extra], check=True)
            staged_count += 1
    except subprocess.CalledProcessError as e:
        print(f"  ! skipped job {jid}: {e}", file=sys.stderr)
        continue
print(f"  → {staged_count}/{len(accepted)} staged")
PY

echo "[7/7] summary"
"$PYTHON" <<PY
import json
raw = len(json.load(open("$RUN_DIR/jobs_raw.json")))
filtered = len(json.load(open("$RUN_DIR/jobs_filtered.json")))
matched = json.load(open("$RUN_DIR/jobs_matched.json"))
accepted = [j for j in matched if j["llm_score"]["final_score"] >= float("$ACCEPT_THRESHOLD")]
print(f"  search:    {raw} jobs")
print(f"  pre-filter:{filtered} passed")
print(f"  llm-scored:{len(matched)}")
print(f"  accepted:  {len(accepted)} (score ≥ $ACCEPT_THRESHOLD)")
print()
print("Next:")
for j in accepted:
    print(f"  open temp/outputs/applications/{j['job_id']}__*/apply_url.txt")
    print(f"  python -m tools.application.mark_submitted {j['job_id']}")
PY
