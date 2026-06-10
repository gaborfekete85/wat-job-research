#!/usr/bin/env bash
# Offline E2E: stubs the LLM and uses cached LinkedIn HTML. Confirms the
# pipeline writes a non-empty PDF and adds a CSV row.
set -euo pipefail

# Resolve project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="$PROJECT_ROOT/.venv/bin/python"
cd "$PROJECT_ROOT"

WORK=$(mktemp -d)
trap "rm -rf $WORK" EXIT

# Minimal fake profile
cat > "$WORK/profile.md" <<'EOF'
---
name: "Test User"
title: "Engineer"
email: "t@e.st"
phone: "+1-202-555-0100"
location: "Zurich"
summary: "Engineer with AWS and Kafka."
skills:
  cloud_devops: [AWS, Kafka]
experience:
  - company: A
    role: R
    start: "2022"
    end: "now"
    location: Z
    highlights: [h1]
    keywords: [AWS]
---
body
EOF

# Stub a JD
cat > "$WORK/jd.json" <<'EOF'
{ "job_id": "X1", "title": "Backend Eng", "company": "Acme",
  "location": "Zurich", "url": "https://x", "apply_url": "https://x/apply",
  "description": "AWS Kafka required.", "seniority": "Senior",
  "employment_type": "FT", "job_function": "Eng", "industry": "Tech" }
EOF

# Match result with full emphasis structure
cat > "$WORK/match.json" <<'EOF'
{ "final_score": 0.9, "skills_match": 0.9, "seniority_fit": "fit",
  "location_fit": true, "matched_skills": ["AWS","Kafka"],
  "missing_critical": [], "reasoning": "Test.",
  "suggested_emphasis": { "tailored_summary": "Tailored.",
    "priority_skills": ["AWS","Kafka"], "priority_experiences": [0],
    "priority_bullets": {"0": [0]} } }
EOF

# Tailor
"$PYTHON" -m tools.cv.tailor --profile "$WORK/profile.md" --match-result "$WORK/match.json" -o "$WORK/tailored.yml"
test -s "$WORK/tailored.yml"

# Render
"$PYTHON" -m tools.cv.render "$WORK/tailored.yml" -o "$WORK/cv.pdf"
test -s "$WORK/cv.pdf"

# Stage (in an isolated cwd so we don't pollute real applications)
pushd "$WORK" > /dev/null
PYTHONPATH="$PROJECT_ROOT" "$PYTHON" -m tools.application.stage --job-details "$WORK/jd.json" --cv "$WORK/cv.pdf" --match-result "$WORK/match.json"
test -d "temp/outputs/applications" && ls temp/outputs/applications/X1__*/
test -f "temp/outputs/applications/applications.csv"
popd > /dev/null

echo "SMOKE OK"
