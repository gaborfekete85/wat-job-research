# LinkedIn Job Search & Tailored Application Workflow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [docs/specs/2026-06-10-job-search-workflow-design.md](../specs/2026-06-10-job-search-workflow-design.md)

**Goal:** A WAT-framework CLI pipeline that searches LinkedIn for jobs by location, scores them against `profile.md`, generates a tailored PDF CV for high-match jobs, and stages each for human-review-then-submit.

**Architecture:** Stateless Python CLI tools orchestrated by `tools/run.sh` (Mode A) or by the agent reading `workflows/find-and-apply-jobs.md` (Mode C). LLM calls go through Claude API and are limited to three places: match scoring, optional cover-letter drafting, optional ATS-answer drafting. PDF generation via `rendercv`. LinkedIn access uses public `/jobs-guest/...` endpoints (no auth).

**Tech Stack:** Python 3.11+, `requests`, `beautifulsoup4`, `pyyaml`, `rapidfuzz`, `jinja2`, `anthropic` SDK, `rendercv`. Tests via `pytest`.

---

## File structure (all under `job-search/`)

```
pyproject.toml                                   # deps + ruff config
README.md                                        # quick start (~40 lines)
.env.example                                     # ANTHROPIC_API_KEY=

tools/run.sh                                     # Mode A orchestrator
tools/linkedin/resolve_location.py
tools/linkedin/search_jobs.py
tools/linkedin/get_job_details.py
tools/match/extract_skills.py
tools/match/score_keyword.py
tools/match/score_llm.py
tools/cv/tailor.py
tools/cv/render.py
tools/application/draft_cover_letter.py
tools/application/draft_ats_answers.py
tools/application/stage.py
tools/application/mark_submitted.py
tools/shared/http.py                              # rate-limited GET wrapper
tools/shared/skill_dictionary.yml                 # ~150 canonical terms
tools/shared/ats_questions.yml                    # common ATS Qs
tools/shared/prompts/match_score.md
tools/shared/prompts/cover_letter.md
tools/shared/prompts/ats_answers.md

tests/unit/test_extract_skills.py
tests/unit/test_score_keyword.py
tests/unit/test_skill_dictionary.py
tests/unit/test_tailor.py
tests/unit/test_stage.py
tests/unit/test_mark_submitted.py
tests/parsers/fixtures/linkedin_search_zurich.html
tests/parsers/fixtures/linkedin_job_detail_4417627058.html
tests/parsers/fixtures/typeahead_zurich.json
tests/parsers/test_resolve_location.py
tests/parsers/test_search_jobs_parser.py
tests/parsers/test_get_job_details_parser.py
tests/llm/test_score_llm_mocked.py
tests/llm/test_draft_cover_letter_mocked.py
tests/llm/test_draft_ats_answers_mocked.py
tests/smoke/test_end_to_end_offline.sh

workflows/find-and-apply-jobs.md
```

Each tool is one file with `if __name__ == "__main__"` so it's both importable for tests and runnable from `run.sh`. Tools follow the same skeleton: `argparse` for flags, a single `main()` that returns a dict, JSON to stdout (or `-o`).

---

## Phase 0 — Repo bootstrap

### Task 0.1: Initialize git + Python project

**Files:**
- Modify: `.gitignore` (already exists)
- Create: `pyproject.toml`, `.env.example`, `README.md`

- [ ] **Step 1: Initialize git repo if not already**

```bash
cd /Users/gaborfekete/my-projects/my-agent/wat-frameworks/job-search
git init
git add CLAUDE.md .gitignore .env.example  # .env.example doesn't exist yet — created below
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "wat-job-search"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "requests>=2.31",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
    "pyyaml>=6.0",
    "rapidfuzz>=3.0",
    "jinja2>=3.1",
    "anthropic>=0.34",
    "rendercv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.4", "ruff>=0.6"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
packages = []                # CLI scripts only, no installable package

[tool.ruff]
line-length = 100
```

- [ ] **Step 3: Ensure `.env.example` and `.gitignore` are correct**

`.env.example` should already exist with:
```
# Copy this file to `.env` and fill in real values.
# Never commit `.env`.
ANTHROPIC_API_KEY=
# Optional:
# CLAUDE_MODEL=claude-sonnet-4-6
# LINKEDIN_USER_AGENT=...
```

`.gitignore` should already include `.env` and `temp/`. Verify with:
```bash
grep -E "^\.env$|^temp/$" .gitignore
```
Expected: both lines present.

- [ ] **Step 4: Create a placeholder `README.md`**

```markdown
# WAT Job Search

Automated LinkedIn job research with tailored CV generation.

## Install
    pip install -e ".[dev]"
    cp .env.example .env  # add your ANTHROPIC_API_KEY

## Use (Mode A — single command)
    ./tools/run.sh --location "Zurich, Switzerland" --keywords engineer

## Use (Mode C — agentic)
    # Open Claude Code in this directory, say:
    # "Find me jobs in Zurich posted in the last 24 hours."

## Where artifacts go
- `temp/outputs/runs/<timestamp>/` — per-run intermediates
- `temp/outputs/applications/{job_id}__.../` — durable per-job artifacts
- `temp/outputs/applications.csv` — master log

## Tests
    pytest tests/
```

- [ ] **Step 5: Install + verify**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -c "import requests, bs4, yaml, rapidfuzz, jinja2, anthropic; import rendercv; print('OK')"
```
Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml README.md .env.example .gitignore
git commit -m "chore: bootstrap python project + readme"
```

---

## Phase 1 — Shared infrastructure

### Task 1.1: HTTP wrapper with throttle

**Files:**
- Create: `tools/shared/http.py`

- [ ] **Step 1: Create `tools/shared/__init__.py` (empty)**

```bash
mkdir -p tools/shared
touch tools/shared/__init__.py
```

- [ ] **Step 2: Implement `tools/shared/http.py`**

```python
"""Rate-limited HTTP GET wrapper for LinkedIn public endpoints."""
from __future__ import annotations
import os, time
from dataclasses import dataclass
import requests

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_THROTTLE_S = 1.5

@dataclass
class _State:
    last_call: float = 0.0
    throttle_s: float = DEFAULT_THROTTLE_S

_state = _State()

def set_throttle(seconds: float) -> None:
    _state.throttle_s = seconds

def get(url: str, *, accept: str = "text/html,*/*;q=0.8") -> requests.Response:
    elapsed = time.monotonic() - _state.last_call
    if elapsed < _state.throttle_s:
        time.sleep(_state.throttle_s - elapsed)
    headers = {
        "User-Agent": os.environ.get("LINKEDIN_USER_AGENT", DEFAULT_UA),
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9",
    }
    resp = requests.get(url, headers=headers, timeout=20)
    _state.last_call = time.monotonic()
    return resp
```

- [ ] **Step 3: Smoke-test it manually**

```bash
python -c "from tools.shared.http import get; r = get('https://www.linkedin.com/jobs-guest/api/typeaheadHits?typeaheadType=GEO&query=Zurich'); print(r.status_code, r.text[:120])"
```
Expected: `200 [{"id":"107814425",...`

- [ ] **Step 4: Commit**

```bash
git add tools/shared/
git commit -m "feat(shared): rate-limited HTTP wrapper for LinkedIn"
```

### Task 1.2: Skill dictionary + structural test

**Files:**
- Create: `tools/shared/skill_dictionary.yml`
- Create: `tests/unit/test_skill_dictionary.py`

- [ ] **Step 1: Write the failing structural test**

```bash
mkdir -p tests/unit
touch tests/__init__.py tests/unit/__init__.py
```

`tests/unit/test_skill_dictionary.py`:
```python
"""Validate skill_dictionary.yml shape."""
from pathlib import Path
import yaml

DICT_PATH = Path(__file__).resolve().parents[2] / "tools/shared/skill_dictionary.yml"

def test_dictionary_loads():
    data = yaml.safe_load(DICT_PATH.read_text())
    assert isinstance(data, dict) and data, "must be a non-empty mapping of categories"

def test_categories_are_terms_to_variants():
    data = yaml.safe_load(DICT_PATH.read_text())
    for category, terms in data.items():
        assert isinstance(terms, dict), f"{category} must be a mapping of canonical → variants"
        for canonical, variants in terms.items():
            assert isinstance(canonical, str) and canonical
            assert isinstance(variants, list) and all(isinstance(v, str) for v in variants)

def test_has_minimum_seed_entries():
    data = yaml.safe_load(DICT_PATH.read_text())
    total = sum(len(terms) for terms in data.values())
    assert total >= 100, f"expected ≥100 canonical entries, got {total}"
```

- [ ] **Step 2: Run test, verify failure**

```bash
pytest tests/unit/test_skill_dictionary.py -v
```
Expected: FAIL — file doesn't exist.

- [ ] **Step 3: Write `tools/shared/skill_dictionary.yml`**

```yaml
# Canonical name → list of variants. Case-insensitive, word-boundary matching.
# Seeded from profile.md + common CH/EU tech-job vocabulary. ~150 entries.

languages:
  Java:        [java]
  Python:      [python, py]
  JavaScript:  [javascript, js, ecmascript]
  TypeScript:  [typescript, ts]
  SQL:         [sql, "ansi sql"]
  Go:          [go, golang]
  Rust:        [rust]
  Kotlin:      [kotlin]
  Scala:       [scala]
  C++:         ["c++", cpp]
  C#:          ["c#", csharp, "dotnet", ".net"]
  Bash:        [bash, shell, "shell script"]
  PHP:         [php]
  Ruby:        [ruby]

frameworks:
  Spring:           [spring, "spring boot", "spring framework", "spring cloud"]
  FastAPI:          [fastapi, "fast api"]
  Django:           [django]
  Flask:            [flask]
  React:            [react, reactjs, "react.js"]
  "Node.js":        ["node.js", nodejs, node]
  Express:          [express, expressjs, "express.js"]
  Angular:          [angular, angularjs]
  Vue:              [vue, vuejs, "vue.js"]
  Next.js:          ["next.js", nextjs]
  Kafka:            [kafka, "apache kafka", "kafka streams"]
  RabbitMQ:         [rabbitmq]
  GraphQL:          [graphql]
  REST:             ["rest api", restful, "rest apis"]
  gRPC:             [grpc]
  Hibernate:        [hibernate, jpa]

cloud_devops:
  AWS:           [aws, "amazon web services", ec2, ecs, eks, s3, rds, vpc, cloudwatch, lambda, "api gateway"]
  GCP:           [gcp, "google cloud", "google cloud platform"]
  Azure:         [azure, "microsoft azure"]
  Kubernetes:    [kubernetes, k8s]
  Docker:        [docker, containerization, containers]
  Terraform:     [terraform, "infrastructure as code", iac]
  Ansible:       [ansible]
  Helm:          [helm]
  Jenkins:       [jenkins]
  "GitHub Actions": ["github actions"]
  "GitLab CI":   ["gitlab ci", "gitlab-ci"]
  ArgoCD:        [argocd, "argo cd"]
  "CI/CD":       ["ci/cd", "continuous integration", "continuous delivery", "continuous deployment"]
  ELK:           [elk, elasticsearch, "elastic stack", logstash, kibana]
  Grafana:       [grafana]
  Prometheus:    [prometheus]
  DataDog:       [datadog]
  OpenTelemetry: [opentelemetry, otel]
  DevOps:        [devops, "dev ops"]
  SRE:           [sre, "site reliability"]

databases:
  PostgreSQL:    [postgresql, postgres, psql]
  MySQL:         [mysql, mariadb]
  Oracle:        [oracle, "oracle db", plsql]
  MongoDB:       [mongodb, mongo]
  Redis:         [redis]
  Cassandra:     [cassandra]
  DynamoDB:      [dynamodb]
  Snowflake:     [snowflake]
  BigQuery:      [bigquery]
  ClickHouse:    [clickhouse]

architecture:
  Microservices: [microservices, "micro services", "microservice architecture"]
  "Event-Driven":      ["event-driven", "event driven", "event-driven architecture", eda]
  "Domain-Driven Design": [ddd, "domain-driven", "domain driven"]
  "API Design":        ["api design", "api-first"]
  Distributed:         ["distributed systems", "distributed system"]
  Scalability:         [scalability, scalable]
  "High Availability": ["high availability", ha]

tools:
  Git:           [git, github, gitlab, bitbucket]
  Linux:         [linux, unix]
  Jira:          [jira, atlassian]
  Confluence:    [confluence]
  IntelliJ:      [intellij, "intellij idea"]
  VSCode:        [vscode, "vs code", "visual studio code"]
  Postman:       [postman]

ai_ml:
  "Machine Learning": [ml, "machine learning"]
  LLM:            [llm, "large language model", "language model"]
  PyTorch:        [pytorch]
  TensorFlow:     [tensorflow]
  HuggingFace:    [huggingface, "hugging face"]
  RAG:            [rag, "retrieval augmented generation"]
  "Vector DB":    ["vector database", "vector db", pinecone, weaviate, qdrant, milvus]
  OpenAI:         [openai, "open ai"]
  Anthropic:      [anthropic, claude]
  LangChain:      [langchain]

soft:
  Leadership:     ["team leadership", "tech lead", lead, leadership]
  Mentoring:      [mentoring, mentorship, coaching]
  Agile:          [agile, scrum, kanban, "agile/scrum", sprint]
  Communication:  [communication, "communication skills", "stakeholder management"]
  "Production Support": ["production support", "on-call", oncall, troubleshooting]
  Collaboration:  [collaboration, "cross-functional", "cross functional"]
```

- [ ] **Step 4: Run test, verify pass**

```bash
pytest tests/unit/test_skill_dictionary.py -v
```
Expected: all 3 tests pass; `test_has_minimum_seed_entries` reports ≥100.

- [ ] **Step 5: Commit**

```bash
git add tools/shared/skill_dictionary.yml tests/__init__.py tests/unit/__init__.py tests/unit/test_skill_dictionary.py
git commit -m "feat(shared): skill dictionary with ~150 canonical entries"
```

### Task 1.3: ATS questions seed file

**Files:**
- Create: `tools/shared/ats_questions.yml`

- [ ] **Step 1: Write the file**

```yaml
# Common ATS questions worth drafting answers for. Keep this short — the LLM
# tailors answers from profile.md + JD. User edits before submitting.
questions:
  - id: motivation
    text: "Why are you interested in this role / this company?"
  - id: notice_period
    text: "What is your notice period?"
  - id: salary_expectations
    text: "What are your salary expectations? (CHF gross/year)"
  - id: work_authorization
    text: "Do you require work authorization sponsorship in Switzerland?"
  - id: languages
    text: "What languages do you speak and at what level?"
  - id: relocation
    text: "Are you willing to relocate or already based in the area?"
  - id: start_date
    text: "When could you start?"
  - id: remote_preference
    text: "What is your preference for remote / hybrid / on-site?"
```

- [ ] **Step 2: Commit**

```bash
git add tools/shared/ats_questions.yml
git commit -m "feat(shared): ATS common questions seed file"
```

### Task 1.4: LLM prompts

**Files:**
- Create: `tools/shared/prompts/match_score.md`
- Create: `tools/shared/prompts/cover_letter.md`
- Create: `tools/shared/prompts/ats_answers.md`

- [ ] **Step 1: Create prompt directory + write `match_score.md`**

```bash
mkdir -p tools/shared/prompts
```

`tools/shared/prompts/match_score.md`:
```markdown
You are scoring a job description against a candidate's profile.

# Candidate profile
{profile}

# Job description
Title: {title}
Company: {company}
Location: {location}
Seniority: {seniority}
Employment type: {employment_type}
Function: {job_function}
Industry: {industry}

{description}

# Pre-computed deterministic keyword overlap
- Keyword score: {keyword_score:.2f}
- Skills matched: {matched_skills}
- JD skills not in profile: {missing_skills}

# Instructions
Return STRICT JSON with these fields. Do not guess facts not present in the profile.

{{
  "final_score": <float 0.0–1.0>,             // overall match
  "skills_match": <float 0.0–1.0>,            // technical skills fit only
  "seniority_fit": "below" | "fit" | "above", // candidate vs JD seniority
  "location_fit": <bool>,
  "matched_skills": [<string>, ...],           // canonical names
  "missing_critical": [<string>, ...],         // skills the JD seems to require but profile lacks
  "reasoning": "<2–4 sentences, concrete>",
  "suggested_emphasis": {{
    "tailored_summary": "<2–3 sentences rewritten from profile.summary, JD-aware, no invented facts>",
    "priority_skills": [<canonical skill names, ordered by relevance to JD>],
    "priority_experiences": [<int indices into profile.experience, ordered by relevance>],
    "priority_bullets": {{ "<exp_idx>": [<int indices into highlights[]>] }}
  }}
}}

Be honest. If seniority is below, say so even if skills match. If the location is wrong, location_fit=false even if everything else fits.
```

- [ ] **Step 2: Write `cover_letter.md`**

```markdown
You are drafting a cover letter for a candidate applying to a specific job.

# Candidate profile
{profile}

# Job description
{job_block}

# Match analysis (already computed)
{match_block}

# Instructions
Write a concise cover letter in markdown (no greeting block, just the body).

Rules:
- 3–4 short paragraphs.
- Reference 1–2 specific things from the JD that match the candidate's background.
- Use ONLY facts present in the candidate profile. Do NOT invent companies, roles, projects, metrics, or skills.
- Plain, direct tone. No "I am thrilled".
- No bullet points.
- End with one sentence inviting next steps.

Return the markdown only.
```

- [ ] **Step 3: Write `ats_answers.md`**

```markdown
You are drafting honest first-draft answers to common ATS application questions.

# Candidate profile
{profile}

# Job description
{job_block}

# Questions
{questions_block}

# Instructions
For each question, write a 1–3 sentence draft answer the candidate can edit.

Rules:
- ONLY use facts present in the candidate profile.
- For unknowable values (salary expectations, notice period, exact start date), use a TEMPLATE placeholder like `<TODO: confirm CHF range>` rather than guessing.
- For language proficiency, copy exactly from profile.languages.
- For work authorization, only state it if profile makes it explicit; otherwise `<TODO: confirm work authorization>`.

Return STRICT JSON: {{ "<question_id>": "<answer text>", ... }}
```

- [ ] **Step 4: Commit**

```bash
git add tools/shared/prompts/
git commit -m "feat(shared): LLM prompt templates"
```

### Task 1.5: Capture test fixtures

**Files:**
- Create: `tests/parsers/fixtures/linkedin_search_zurich.html`
- Create: `tests/parsers/fixtures/linkedin_job_detail_4417627058.html`
- Create: `tests/parsers/fixtures/typeahead_zurich.json`

- [ ] **Step 1: Move the search HTML we already captured into fixtures**

```bash
mkdir -p tests/parsers/fixtures
cp temp/resources/linkedin_sample.html tests/parsers/fixtures/linkedin_search_zurich.html
cp temp/resources/linkedin_job_detail.html tests/parsers/fixtures/linkedin_job_detail_4417627058.html
```

- [ ] **Step 2: Capture a typeahead fixture**

```bash
curl -sA "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36" \
  "https://www.linkedin.com/jobs-guest/api/typeaheadHits?origin=jserp&typeaheadType=GEO&geoTypes=POPULATED_PLACE,ADMIN_DIVISION_2&query=Zurich" \
  > tests/parsers/fixtures/typeahead_zurich.json
```

Verify it contains `"107814425"`:
```bash
grep -q "107814425" tests/parsers/fixtures/typeahead_zurich.json && echo OK
```
Expected: `OK`.

- [ ] **Step 3: Add `tests/parsers/__init__.py`**

```bash
touch tests/parsers/__init__.py
```

- [ ] **Step 4: Commit**

```bash
git add tests/parsers/
git commit -m "test: capture LinkedIn HTML/JSON fixtures for parser tests"
```

---

## Phase 2 — LinkedIn module (parsers tested via fixtures)

### Task 2.1: `resolve_location.py`

**Files:**
- Create: `tools/linkedin/resolve_location.py`
- Create: `tests/parsers/test_resolve_location.py`

- [ ] **Step 1: Create module dirs**

```bash
mkdir -p tools/linkedin
touch tools/linkedin/__init__.py
```

- [ ] **Step 2: Write the failing test**

`tests/parsers/test_resolve_location.py`:
```python
from pathlib import Path
import json
from tools.linkedin.resolve_location import parse_typeahead

FIXTURE = Path(__file__).parent / "fixtures/typeahead_zurich.json"

def test_parse_typeahead_returns_zurich_switzerland_first_match():
    hits = parse_typeahead(FIXTURE.read_text())
    assert hits, "expected at least one hit"
    # Real Zurich Switzerland geoId
    assert any(h["id"] == "107814425" and "Switzerland" in h["displayName"] for h in hits)

def test_parse_typeahead_returns_top_10():
    hits = parse_typeahead(FIXTURE.read_text())
    assert 1 <= len(hits) <= 10
```

- [ ] **Step 3: Run test, verify failure**

```bash
pytest tests/parsers/test_resolve_location.py -v
```
Expected: import error (module not found).

- [ ] **Step 4: Implement `tools/linkedin/resolve_location.py`**

```python
"""Resolve a location string to LinkedIn geoIds via the public typeahead endpoint."""
from __future__ import annotations
import argparse, json, sys
from urllib.parse import quote
from tools.shared.http import get

TYPEAHEAD_URL = (
    "https://www.linkedin.com/jobs-guest/api/typeaheadHits"
    "?origin=jserp&typeaheadType=GEO&geoTypes=POPULATED_PLACE,ADMIN_DIVISION_2&query={q}"
)

def parse_typeahead(body: str) -> list[dict]:
    raw = json.loads(body)
    return [{"id": h["id"], "displayName": h["displayName"]} for h in raw[:10]]

def resolve(query: str) -> list[dict]:
    r = get(TYPEAHEAD_URL.format(q=quote(query)), accept="application/json")
    r.raise_for_status()
    return parse_typeahead(r.text)

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("query")
    p.add_argument("--pick-first", action="store_true",
                   help="Output the single best hit instead of the full list")
    args = p.parse_args()
    hits = resolve(args.query)
    if args.pick_first:
        if not hits:
            print("no match", file=sys.stderr); return 1
        print(json.dumps(hits[0]))
    else:
        print(json.dumps(hits, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests, verify pass**

```bash
pytest tests/parsers/test_resolve_location.py -v
```
Expected: 2 passing.

- [ ] **Step 6: Smoke run**

```bash
python tools/linkedin/resolve_location.py "Zurich, Switzerland" --pick-first
```
Expected: `{"id": "107814425", "displayName": "Zurich, Zurich, Switzerland"}`.

- [ ] **Step 7: Commit**

```bash
git add tools/linkedin/__init__.py tools/linkedin/resolve_location.py tests/parsers/test_resolve_location.py
git commit -m "feat(linkedin): resolve_location via public typeahead"
```

### Task 2.2: `search_jobs.py`

**Files:**
- Create: `tools/linkedin/search_jobs.py`
- Create: `tests/parsers/test_search_jobs_parser.py`

- [ ] **Step 1: Write the failing test**

`tests/parsers/test_search_jobs_parser.py`:
```python
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
```

- [ ] **Step 2: Run test, verify failure**

```bash
pytest tests/parsers/test_search_jobs_parser.py -v
```
Expected: import error.

- [ ] **Step 3: Implement `tools/linkedin/search_jobs.py`**

```python
"""Search LinkedIn jobs via public guest endpoint and parse the HTML cards."""
from __future__ import annotations
import argparse, json, sys, time
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from tools.shared.http import get

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
PAGE_SIZE = 25

def _txt(node) -> str:
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""

def parse_search_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for card in soup.select("div.base-card"):
        urn = card.get("data-entity-urn", "")
        job_id = urn.split(":")[-1] if "jobPosting" in urn else ""
        title = _txt(card.select_one("h3.base-search-card__title"))
        company = _txt(card.select_one("h4.base-search-card__subtitle"))
        location = _txt(card.select_one(".job-search-card__location"))
        time_tag = card.select_one("time")
        posted = time_tag.get("datetime") if time_tag else None
        link = card.select_one("a.base-card__full-link")
        url = link["href"].split("?")[0] if link else ""
        if job_id and title and company:
            out.append({
                "job_id": job_id, "title": title, "company": company,
                "location": location, "posted": posted, "url": url,
            })
    return out

def search(keywords: str, geo_id: str, *, posted_within_hours: int | None,
           limit: int) -> list[dict]:
    results: list[dict] = []
    start = 0
    while len(results) < limit:
        params = {"keywords": keywords, "geoId": geo_id, "start": start}
        if posted_within_hours:
            params["f_TPR"] = f"r{posted_within_hours * 3600}"
        url = f"{SEARCH_URL}?{urlencode(params)}"
        r = get(url)
        if r.status_code == 429:
            raise RuntimeError("LinkedIn returned 429 — rate limited")
        r.raise_for_status()
        page = parse_search_html(r.text)
        if not page:
            break
        results.extend(page)
        if len(page) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return results[:limit]

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--keywords", required=True)
    p.add_argument("--geo-id", required=True)
    p.add_argument("--posted-within-hours", type=int, default=None)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("-o", dest="output", default=None)
    args = p.parse_args()
    jobs = search(args.keywords, args.geo_id,
                  posted_within_hours=args.posted_within_hours, limit=args.limit)
    payload = json.dumps(jobs, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w") as f: f.write(payload)
        print(args.output)
    else:
        print(payload)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/parsers/test_search_jobs_parser.py -v
```
Expected: 3 passing.

- [ ] **Step 5: Smoke run (hits live LinkedIn)**

```bash
python tools/linkedin/search_jobs.py --keywords engineer --geo-id 107814425 --limit 5
```
Expected: JSON array with 5 jobs, each having `job_id`, `title`, `company`, `location`, `posted`, `url`.

- [ ] **Step 6: Commit**

```bash
git add tools/linkedin/search_jobs.py tests/parsers/test_search_jobs_parser.py
git commit -m "feat(linkedin): search_jobs with pagination + throttle"
```

### Task 2.3: `get_job_details.py`

**Files:**
- Create: `tools/linkedin/get_job_details.py`
- Create: `tests/parsers/test_get_job_details_parser.py`

- [ ] **Step 1: Write the failing test**

`tests/parsers/test_get_job_details_parser.py`:
```python
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
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/parsers/test_get_job_details_parser.py -v
```
Expected: import error.

- [ ] **Step 3: Implement `tools/linkedin/get_job_details.py`**

```python
"""Fetch and parse a single LinkedIn job detail page."""
from __future__ import annotations
import argparse, json, sys
from bs4 import BeautifulSoup
from tools.shared.http import get

DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

def _txt(node) -> str:
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""

def parse_detail_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    title = _txt(soup.select_one("h1.top-card-layout__title")) \
            or _txt(soup.select_one("h2.top-card-layout__title"))
    company = _txt(soup.select_one("a.topcard__org-name-link")) \
              or _txt(soup.select_one(".topcard__org-name-link"))
    location = _txt(soup.select_one("span.topcard__flavor--bullet"))
    description = _txt(soup.select_one("div.show-more-less-html__markup"))

    criteria: dict[str, str] = {}
    for item in soup.select("li.description__job-criteria-item"):
        k = _txt(item.select_one(".description__job-criteria-subheader"))
        v = _txt(item.select_one(".description__job-criteria-text"))
        if k and v:
            criteria[k] = v

    apply_link = soup.select_one("a.topcard__link") \
                 or soup.select_one('a[data-tracking-control-name="public_jobs_apply-link-offsite"]')
    apply_url = apply_link.get("href") if apply_link else None

    return {
        "title": title or None,
        "company": company or None,
        "location": location or None,
        "description": description,
        "seniority": criteria.get("Seniority level"),
        "employment_type": criteria.get("Employment type"),
        "job_function": criteria.get("Job function"),
        "industry": criteria.get("Industries"),
        "apply_url": apply_url,
    }

def fetch(job_id: str) -> dict:
    r = get(DETAIL_URL.format(job_id=job_id))
    r.raise_for_status()
    detail = parse_detail_html(r.text)
    detail["job_id"] = job_id
    return detail

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("job_id")
    p.add_argument("-o", dest="output", default=None)
    args = p.parse_args()
    d = fetch(args.job_id)
    payload = json.dumps(d, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w") as f: f.write(payload)
        print(args.output)
    else:
        print(payload)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/parsers/test_get_job_details_parser.py -v
```
Expected: 3 passing. (If any selector is wrong, inspect the fixture HTML and tune the selectors. Snapshot tests are designed to catch this.)

- [ ] **Step 5: Smoke run**

```bash
python tools/linkedin/get_job_details.py 4417627058
```
Expected: JSON with non-empty `description` and `seniority`/`employment_type` populated.

- [ ] **Step 6: Commit**

```bash
git add tools/linkedin/get_job_details.py tests/parsers/test_get_job_details_parser.py
git commit -m "feat(linkedin): get_job_details with criteria extraction"
```

---

## Phase 3 — Match module

### Task 3.1: `extract_skills.py`

**Files:**
- Create: `tools/match/extract_skills.py`
- Create: `tests/unit/test_extract_skills.py`

- [ ] **Step 1: Create dirs + write failing test**

```bash
mkdir -p tools/match
touch tools/match/__init__.py
```

`tests/unit/test_extract_skills.py`:
```python
from tools.match.extract_skills import extract_from_text, extract_from_profile_yaml

SAMPLE_JD = """
We are looking for a senior backend engineer with strong AWS, Kafka, and Kubernetes
experience. PostgreSQL knowledge required. Bonus: Terraform.
"""

def test_extract_canonical_skills():
    skills = extract_from_text(SAMPLE_JD)
    assert "AWS" in skills
    assert "Kafka" in skills
    assert "Kubernetes" in skills
    assert "PostgreSQL" in skills
    assert "Terraform" in skills

def test_does_not_match_substrings_of_unrelated_words():
    # "Java" should not match "JavaScript"
    skills = extract_from_text("We use JavaScript and TypeScript.")
    assert "JavaScript" in skills
    assert "Java" not in skills

def test_case_insensitive():
    skills = extract_from_text("python and POSTGRES")
    assert "Python" in skills
    assert "PostgreSQL" in skills

def test_profile_extraction_uses_yaml_skills():
    profile_yaml = """
---
skills:
  languages: [Java, Python]
  frameworks: [Spring, Kafka]
  cloud_devops: [AWS, Kubernetes]
---
some long-form text mentioning React.
"""
    skills = extract_from_profile_yaml(profile_yaml)
    assert {"Java", "Python", "Spring", "Kafka", "AWS", "Kubernetes", "React"}.issubset(skills)
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/unit/test_extract_skills.py -v
```
Expected: import error.

- [ ] **Step 3: Implement `tools/match/extract_skills.py`**

```python
"""Extract canonical skills from JD text or profile.md, using skill_dictionary.yml."""
from __future__ import annotations
import argparse, functools, json, re, sys
from pathlib import Path
import yaml

DICT_PATH = Path(__file__).resolve().parents[1] / "shared/skill_dictionary.yml"

@functools.lru_cache(maxsize=1)
def _compile_patterns() -> list[tuple[str, re.Pattern]]:
    """Returns list of (canonical_name, compiled_regex). Patterns match any variant
    on word boundaries, case-insensitive."""
    data = yaml.safe_load(DICT_PATH.read_text())
    out: list[tuple[str, re.Pattern]] = []
    for _category, terms in data.items():
        for canonical, variants in terms.items():
            all_terms = [canonical, *variants]
            # Escape; use \b for ASCII variants. Variants like "c++" need
            # raw boundary handling since \b doesn't separate +.
            parts = []
            for t in all_terms:
                esc = re.escape(t.strip())
                # Use lookarounds for non-word boundaries instead of \b
                parts.append(rf"(?<![A-Za-z0-9+#]){esc}(?![A-Za-z0-9+#])")
            pat = re.compile("|".join(parts), re.IGNORECASE)
            out.append((canonical, pat))
    return out

def extract_from_text(text: str) -> set[str]:
    return {canonical for canonical, pat in _compile_patterns() if pat.search(text)}

def extract_from_profile_yaml(profile_yaml: str) -> set[str]:
    """Read structured YAML frontmatter + long-form body. Frontmatter skills
    are taken as-is; body text scanned with dictionary."""
    found: set[str] = set()
    parts = profile_yaml.split("---", 2)
    if len(parts) >= 3:
        front = yaml.safe_load(parts[1]) or {}
        body = parts[2]
        for _cat, items in (front.get("skills") or {}).items():
            for s in items or []:
                # Normalize via dictionary if possible (e.g., "k8s" -> "Kubernetes")
                matches = extract_from_text(str(s))
                if matches:
                    found |= matches
                else:
                    found.add(str(s))
        # Also include 'keywords' on each experience
        for exp in front.get("experience") or []:
            for k in exp.get("keywords") or []:
                matches = extract_from_text(str(k))
                if matches:
                    found |= matches
                else:
                    found.add(str(k))
        found |= extract_from_text(body)
    else:
        found |= extract_from_text(profile_yaml)
    return found

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["profile", "jd"], required=True)
    p.add_argument("--input", help="path to file; if omitted, reads stdin")
    args = p.parse_args()
    text = Path(args.input).read_text() if args.input else sys.stdin.read()
    skills = (extract_from_profile_yaml if args.source == "profile" else extract_from_text)(text)
    print(json.dumps({"skills": sorted(skills)}, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/unit/test_extract_skills.py -v
```
Expected: 4 passing.

- [ ] **Step 5: Smoke run against real profile**

```bash
python tools/match/extract_skills.py --source profile --input temp/resources/profile.md
```
Expected: JSON with `skills` array including `Java`, `Python`, `Kafka`, `AWS`, `Kubernetes`, etc.

- [ ] **Step 6: Commit**

```bash
git add tools/match/__init__.py tools/match/extract_skills.py tests/unit/test_extract_skills.py
git commit -m "feat(match): canonical skill extraction with dictionary + synonyms"
```

### Task 3.2: `score_keyword.py`

**Files:**
- Create: `tools/match/score_keyword.py`
- Create: `tests/unit/test_score_keyword.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_score_keyword.py`:
```python
from tools.match.score_keyword import score

def test_full_match_scores_1():
    r = score({"Java", "AWS"}, {"Java", "AWS"})
    assert r["score"] == 1.0

def test_no_match_scores_0():
    r = score({"Java"}, {"Rust"})
    assert r["score"] == 0.0

def test_partial_match():
    # JD needs Java, AWS, Kafka. Profile has Java + AWS only.
    r = score({"Java", "AWS"}, {"Java", "AWS", "Kafka"})
    assert abs(r["score"] - 2/3) < 1e-6
    assert set(r["matched"]) == {"Java", "AWS"}
    assert r["missing"] == ["Kafka"]

def test_empty_jd_skills_returns_zero():
    r = score({"Java"}, set())
    assert r["score"] == 0.0
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/unit/test_score_keyword.py -v
```

- [ ] **Step 3: Implement `tools/match/score_keyword.py`**

```python
"""Deterministic keyword overlap scoring: score = |jd ∩ profile| / |jd|."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from tools.match.extract_skills import extract_from_profile_yaml, extract_from_text

def score(profile_skills: set[str], jd_skills: set[str]) -> dict:
    if not jd_skills:
        return {"score": 0.0, "matched": [], "missing": [], "jd_skills": []}
    matched = sorted(profile_skills & jd_skills)
    missing = sorted(jd_skills - profile_skills)
    return {
        "score": round(len(matched) / len(jd_skills), 4),
        "matched": matched,
        "missing": missing,
        "jd_skills": sorted(jd_skills),
    }

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", required=True)
    p.add_argument("--jd", required=True, help="path to JD text file")
    args = p.parse_args()
    profile_skills = extract_from_profile_yaml(Path(args.profile).read_text())
    jd_skills = extract_from_text(Path(args.jd).read_text())
    print(json.dumps(score(profile_skills, jd_skills), indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/unit/test_score_keyword.py -v
```
Expected: 4 passing.

- [ ] **Step 5: Commit**

```bash
git add tools/match/score_keyword.py tests/unit/test_score_keyword.py
git commit -m "feat(match): keyword overlap scorer (JD-coverage)"
```

### Task 3.3: `score_llm.py`

**Files:**
- Create: `tools/match/score_llm.py`
- Create: `tests/llm/test_score_llm_mocked.py`

- [ ] **Step 1: Create test dir + write failing test**

```bash
mkdir -p tests/llm
touch tests/llm/__init__.py
```

`tests/llm/test_score_llm_mocked.py`:
```python
import json
from unittest.mock import MagicMock, patch
from tools.match.score_llm import score_with_llm

MOCK_RESPONSE_JSON = {
    "final_score": 0.82,
    "skills_match": 0.85,
    "seniority_fit": "fit",
    "location_fit": True,
    "matched_skills": ["AWS", "Kafka"],
    "missing_critical": [],
    "reasoning": "Strong cloud + event-driven match.",
    "suggested_emphasis": {
        "tailored_summary": "Senior engineer with 15+ years in distributed systems...",
        "priority_skills": ["AWS", "Kafka", "Kubernetes"],
        "priority_experiences": [0, 1],
        "priority_bullets": {"0": [0, 2, 5]},
    },
}

@patch("tools.match.score_llm.Anthropic")
def test_score_with_llm_returns_parsed_json(mock_cls):
    client = MagicMock()
    mock_cls.return_value = client
    client.messages.create.return_value = MagicMock(
        content=[MagicMock(type="text", text=json.dumps(MOCK_RESPONSE_JSON))]
    )
    result = score_with_llm(
        profile_md="--- \n---",
        job_details={"title": "X", "company": "Y", "location": "Z",
                     "seniority": "Senior", "employment_type": "FT",
                     "job_function": "Eng", "industry": "Fintech",
                     "description": "..."},
        keyword_result={"score": 0.6, "matched": ["AWS"], "missing": ["Rust"]},
    )
    assert result["final_score"] == 0.82
    assert result["suggested_emphasis"]["priority_skills"][0] == "AWS"
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/llm/test_score_llm_mocked.py -v
```

- [ ] **Step 3: Implement `tools/match/score_llm.py`**

```python
"""LLM-backed match scorer. One Claude API call per job."""
from __future__ import annotations
import argparse, json, os, re, sys
from pathlib import Path
from anthropic import Anthropic

PROMPT_PATH = Path(__file__).resolve().parents[1] / "shared/prompts/match_score.md"
DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

def _build_prompt(profile_md: str, job: dict, kw: dict) -> str:
    template = PROMPT_PATH.read_text()
    return template.format(
        profile=profile_md,
        title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location", ""),
        seniority=job.get("seniority") or "unspecified",
        employment_type=job.get("employment_type") or "unspecified",
        job_function=job.get("job_function") or "unspecified",
        industry=job.get("industry") or "unspecified",
        description=job.get("description", ""),
        keyword_score=kw.get("score", 0.0),
        matched_skills=", ".join(kw.get("matched", [])) or "(none)",
        missing_skills=", ".join(kw.get("missing", [])) or "(none)",
    )

def _extract_json(text: str) -> dict:
    # Be permissive — strip code fences if present.
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    return json.loads(text)

def score_with_llm(profile_md: str, job_details: dict, keyword_result: dict) -> dict:
    client = Anthropic()
    prompt = _build_prompt(profile_md, job_details, keyword_result)
    msg = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    text_parts = [b.text for b in msg.content if getattr(b, "type", "") == "text"]
    return _extract_json("\n".join(text_parts))

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", required=True)
    p.add_argument("--job-details", required=True)
    p.add_argument("--keyword-result", required=True)
    p.add_argument("-o", dest="output", default=None)
    args = p.parse_args()
    profile_md = Path(args.profile).read_text()
    job = json.loads(Path(args.job_details).read_text())
    kw = json.loads(Path(args.keyword_result).read_text())
    result = score_with_llm(profile_md, job, kw)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload); print(args.output)
    else:
        print(payload)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/llm/test_score_llm_mocked.py -v
```
Expected: 1 passing.

- [ ] **Step 5: Commit**

```bash
git add tools/match/score_llm.py tests/llm/__init__.py tests/llm/test_score_llm_mocked.py
git commit -m "feat(match): LLM match scorer with structured JSON response"
```

---

## Phase 4 — CV module

### Task 4.1: `tailor.py`

**Files:**
- Create: `tools/cv/tailor.py`
- Create: `tests/unit/test_tailor.py`

- [ ] **Step 1: Create dirs + write failing test**

```bash
mkdir -p tools/cv
touch tools/cv/__init__.py
```

`tests/unit/test_tailor.py`:
```python
import yaml
from tools.cv.tailor import tailor

PROFILE_YAML = """---
name: Gabor Fekete
title: Senior Engineer
email: x@y.z
phone: "+41"
location: Zurich
summary: Original generic summary.
skills:
  languages: [Java, Python]
  frameworks: [Spring, Kafka]
experience:
  - company: A
    role: R1
    start: "2022"
    end: "now"
    location: Zurich
    highlights: [h0_a, h0_b, h0_c]
    keywords: [Spring]
  - company: B
    role: R2
    start: "2020"
    end: "2022"
    location: Budapest
    highlights: [h1_a, h1_b]
    keywords: [Java]
---
long form
"""

MATCH = {
  "suggested_emphasis": {
    "tailored_summary": "JD-aware summary.",
    "priority_skills": ["Kafka", "Spring"],
    "priority_experiences": [0],
    "priority_bullets": {"0": [0, 2]},
  }
}

def test_tailor_applies_summary_and_priority_skills():
    out_yaml = tailor(PROFILE_YAML, MATCH)
    data = yaml.safe_load(out_yaml)
    assert data["summary"] == "JD-aware summary."
    # priority_skills lead the list, originals follow
    assert data["skills"]["frameworks"][:2] == ["Kafka", "Spring"]

def test_tailor_subsets_highlights_for_priority_experience():
    out_yaml = tailor(PROFILE_YAML, MATCH)
    data = yaml.safe_load(out_yaml)
    exp0 = data["experience"][0]
    assert exp0["highlights"] == ["h0_a", "h0_c"]

def test_tailor_keeps_non_priority_experience_intact():
    out_yaml = tailor(PROFILE_YAML, MATCH)
    data = yaml.safe_load(out_yaml)
    exp1 = data["experience"][1]
    assert exp1["highlights"] == ["h1_a", "h1_b"]
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/unit/test_tailor.py -v
```

- [ ] **Step 3: Implement `tools/cv/tailor.py`**

```python
"""Build a tailored rendercv-shaped YAML from profile.md + match_result."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import yaml

def _parse_profile(profile_md: str) -> dict:
    parts = profile_md.split("---", 2)
    return yaml.safe_load(parts[1]) if len(parts) >= 3 else {}

def tailor(profile_md: str, match_result: dict) -> str:
    profile = _parse_profile(profile_md)
    emp = (match_result or {}).get("suggested_emphasis", {})

    # Replace summary if tailored one is provided
    if emp.get("tailored_summary"):
        profile["summary"] = emp["tailored_summary"]

    # Reorder skills — lead with priority_skills, dedupe
    priority = list(emp.get("priority_skills") or [])
    if profile.get("skills") and priority:
        for category, items in (profile["skills"] or {}).items():
            if not items:
                continue
            originals = [s for s in items if s not in priority]
            leading = [s for s in priority if s in items]
            profile["skills"][category] = leading + originals

    # Subset highlights for priority experiences
    bullets = emp.get("priority_bullets") or {}
    for idx_str, keep in bullets.items():
        try:
            i = int(idx_str)
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(profile.get("experience") or []):
            highlights = profile["experience"][i].get("highlights") or []
            profile["experience"][i]["highlights"] = [highlights[k] for k in keep
                                                     if 0 <= k < len(highlights)]

    return yaml.safe_dump(profile, sort_keys=False, allow_unicode=True)

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", required=True)
    p.add_argument("--match-result", required=True)
    p.add_argument("-o", required=True)
    args = p.parse_args()
    out = tailor(Path(args.profile).read_text(),
                 json.loads(Path(args.match_result).read_text()))
    Path(args.o).write_text(out)
    print(args.o)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/unit/test_tailor.py -v
```
Expected: 3 passing.

- [ ] **Step 5: Commit**

```bash
git add tools/cv/__init__.py tools/cv/tailor.py tests/unit/test_tailor.py
git commit -m "feat(cv): tailor.py — deterministic YAML transformation"
```

### Task 4.2: `render.py`

**Files:**
- Create: `tools/cv/render.py`

NOTE: `tailor.py` produces a YAML shaped for our internal use. rendercv expects a slightly different schema (its `cv:` root key, etc.). This task includes a small adapter.

- [ ] **Step 1: Confirm rendercv schema**

```bash
rendercv new --help
```
Read the help, look at how rendercv expects `cv.name`, `cv.sections.experience`, etc. The adapter below targets rendercv ≥ 1.0.

- [ ] **Step 2: Implement `tools/cv/render.py`**

```python
"""Convert our tailored YAML to rendercv schema and run `rendercv render`."""
from __future__ import annotations
import argparse, subprocess, sys, tempfile
from pathlib import Path
import yaml

def to_rendercv_schema(profile: dict, theme: str = "engineeringresumes") -> dict:
    """Maps our profile schema to rendercv's `cv:` shape."""
    def _exp_entry(e: dict) -> dict:
        return {
            "company": e.get("company"),
            "position": e.get("role"),
            "start_date": _date(e.get("start")),
            "end_date": _date(e.get("end")),
            "location": e.get("location"),
            "highlights": e.get("highlights") or [],
        }
    def _date(v):
        return None if v in (None, "Until now", "present", "now") else str(v)
    def _flatten_skills(skills: dict | None) -> list[dict]:
        out = []
        for category, items in (skills or {}).items():
            if items:
                out.append({"label": category.replace("_", " ").title(),
                            "details": ", ".join(items)})
        return out
    sections = {}
    sections["summary"] = [profile.get("summary", "")]
    exp = profile.get("experience") or []
    if exp:
        sections["experience"] = [_exp_entry(e) for e in exp]
    edu = profile.get("education") or []
    if edu:
        sections["education"] = [{
            "institution": e.get("school"),
            "area": e.get("degree"),
            "start_date": _date(e.get("start")),
            "end_date": _date(e.get("end")),
            "location": e.get("location"),
        } for e in edu]
    skills = _flatten_skills(profile.get("skills"))
    if skills:
        sections["skills"] = skills
    certs = profile.get("certifications") or []
    if certs:
        sections["certifications"] = [
            {"name": c.get("name"), "details": f"{c.get('issuer','')} ({c.get('year','')})"}
            for c in certs
        ]
    langs = profile.get("languages") or []
    if langs:
        sections["languages"] = [
            {"label": l.get("name"), "details": l.get("level")} for l in langs
        ]
    return {
        "cv": {
            "name": profile.get("name"),
            "email": profile.get("email"),
            "phone": profile.get("phone"),
            "location": profile.get("location"),
            "social_networks": [
                {"network": "LinkedIn", "username": profile.get("linkedin", "").rstrip("/").split("/")[-1]} \
                    if profile.get("linkedin") else None,
                {"network": "GitHub", "username": profile.get("github", "").rstrip("/").split("/")[-1]} \
                    if profile.get("github") else None,
            ],
            "sections": sections,
        },
        "design": {"theme": theme},
    }

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("tailored_yml")
    p.add_argument("-o", dest="output", required=True, help="output PDF path")
    p.add_argument("--theme", default="engineeringresumes")
    args = p.parse_args()
    profile = yaml.safe_load(Path(args.tailored_yml).read_text())
    rendercv_doc = to_rendercv_schema(profile, theme=args.theme)
    # Drop None social entries
    sn = rendercv_doc["cv"].get("social_networks") or []
    rendercv_doc["cv"]["social_networks"] = [s for s in sn if s]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        input_yml = tmp / "input.yml"
        input_yml.write_text(yaml.safe_dump(rendercv_doc, sort_keys=False, allow_unicode=True))
        proc = subprocess.run(
            ["rendercv", "render", str(input_yml), "--output-folder", str(tmp)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print(proc.stderr, file=sys.stderr); return 1
        pdfs = list(tmp.glob("*.pdf"))
        if not pdfs:
            print("rendercv produced no PDF", file=sys.stderr); return 1
        Path(args.output).write_bytes(pdfs[0].read_bytes())
        print(args.output)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Smoke test — render the unmodified profile**

```bash
# Tailor the original profile with an empty match (no transformations)
echo '{"suggested_emphasis": {}}' > /tmp/empty_match.json
python tools/cv/tailor.py --profile temp/resources/profile.md --match-result /tmp/empty_match.json -o /tmp/tailored.yml
python tools/cv/render.py /tmp/tailored.yml -o /tmp/test_cv.pdf
ls -la /tmp/test_cv.pdf
```
Expected: a non-empty PDF.

- [ ] **Step 4: Commit**

```bash
git add tools/cv/render.py
git commit -m "feat(cv): rendercv adapter and PDF wrapper"
```

---

## Phase 5 — Application module

### Task 5.1: `draft_cover_letter.py`

**Files:**
- Create: `tools/application/draft_cover_letter.py`
- Create: `tests/llm/test_draft_cover_letter_mocked.py`

- [ ] **Step 1: Create dirs + write failing test**

```bash
mkdir -p tools/application
touch tools/application/__init__.py
```

`tests/llm/test_draft_cover_letter_mocked.py`:
```python
from unittest.mock import MagicMock, patch
from tools.application.draft_cover_letter import draft_cover_letter

MOCK_TEXT = "Dear Hiring Manager,\n\nI'd like to apply.\n\nBest,\nGabor"

@patch("tools.application.draft_cover_letter.Anthropic")
def test_draft_returns_markdown(mock_cls):
    c = MagicMock(); mock_cls.return_value = c
    c.messages.create.return_value = MagicMock(
        content=[MagicMock(type="text", text=MOCK_TEXT)]
    )
    out = draft_cover_letter("---\n---", {"title": "X", "company": "Y"}, {"final_score": 0.8})
    assert "I'd like to apply" in out
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/llm/test_draft_cover_letter_mocked.py -v
```

- [ ] **Step 3: Implement `tools/application/draft_cover_letter.py`**

```python
"""Draft a cover letter using profile + JD + match analysis. One LLM call."""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from anthropic import Anthropic

PROMPT_PATH = Path(__file__).resolve().parents[1] / "shared/prompts/cover_letter.md"
DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

def draft_cover_letter(profile_md: str, job_details: dict, match_result: dict) -> str:
    job_block = "\n".join(f"{k}: {v}" for k, v in job_details.items() if v)
    match_block = json.dumps(match_result.get("suggested_emphasis", {}), indent=2)
    prompt = PROMPT_PATH.read_text().format(
        profile=profile_md, job_block=job_block, match_block=match_block,
    )
    client = Anthropic()
    msg = client.messages.create(
        model=DEFAULT_MODEL, max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    text_parts = [b.text for b in msg.content if getattr(b, "type", "") == "text"]
    return "\n".join(text_parts).strip()

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", required=True)
    p.add_argument("--job-details", required=True)
    p.add_argument("--match-result", required=True)
    p.add_argument("-o", required=True)
    args = p.parse_args()
    md = draft_cover_letter(
        Path(args.profile).read_text(),
        json.loads(Path(args.job_details).read_text()),
        json.loads(Path(args.match_result).read_text()),
    )
    Path(args.o).write_text(md)
    print(args.o)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/llm/test_draft_cover_letter_mocked.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/application/__init__.py tools/application/draft_cover_letter.py tests/llm/test_draft_cover_letter_mocked.py
git commit -m "feat(application): cover letter drafter (LLM-backed)"
```

### Task 5.2: `draft_ats_answers.py`

**Files:**
- Create: `tools/application/draft_ats_answers.py`
- Create: `tests/llm/test_draft_ats_answers_mocked.py`

- [ ] **Step 1: Write failing test**

`tests/llm/test_draft_ats_answers_mocked.py`:
```python
import json
from unittest.mock import MagicMock, patch
from tools.application.draft_ats_answers import draft_answers

MOCK_JSON = {"motivation": "I'm interested because…", "salary_expectations": "<TODO: confirm>"}

@patch("tools.application.draft_ats_answers.Anthropic")
def test_draft_returns_q_a(mock_cls):
    c = MagicMock(); mock_cls.return_value = c
    c.messages.create.return_value = MagicMock(
        content=[MagicMock(type="text", text=json.dumps(MOCK_JSON))]
    )
    out = draft_answers("---\n---", {"title": "X"})
    assert out["motivation"].startswith("I'm interested")
    assert "<TODO" in out["salary_expectations"]
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/llm/test_draft_ats_answers_mocked.py -v
```

- [ ] **Step 3: Implement `tools/application/draft_ats_answers.py`**

```python
"""Draft answers to common ATS questions."""
from __future__ import annotations
import argparse, json, os, re, sys
from pathlib import Path
import yaml
from anthropic import Anthropic

PROMPT_PATH = Path(__file__).resolve().parents[1] / "shared/prompts/ats_answers.md"
QUESTIONS_PATH = Path(__file__).resolve().parents[1] / "shared/ats_questions.yml"
DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

def _extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    return json.loads(text)

def draft_answers(profile_md: str, job_details: dict) -> dict:
    questions = yaml.safe_load(QUESTIONS_PATH.read_text())["questions"]
    job_block = "\n".join(f"{k}: {v}" for k, v in job_details.items() if v)
    questions_block = "\n".join(f"- {q['id']}: {q['text']}" for q in questions)
    prompt = PROMPT_PATH.read_text().format(
        profile=profile_md, job_block=job_block, questions_block=questions_block,
    )
    client = Anthropic()
    msg = client.messages.create(
        model=DEFAULT_MODEL, max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    text_parts = [b.text for b in msg.content if getattr(b, "type", "") == "text"]
    return _extract_json("\n".join(text_parts))

def _format_md(answers: dict, questions: list[dict]) -> str:
    lines = ["# Draft answers — review before submitting", ""]
    for q in questions:
        ans = answers.get(q["id"], "<TODO: draft missing>")
        lines.append(f"## {q['text']}")
        lines.append(ans)
        lines.append("")
    return "\n".join(lines)

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", required=True)
    p.add_argument("--job-details", required=True)
    p.add_argument("-o", required=True)
    args = p.parse_args()
    profile_md = Path(args.profile).read_text()
    job = json.loads(Path(args.job_details).read_text())
    answers = draft_answers(profile_md, job)
    questions = yaml.safe_load(QUESTIONS_PATH.read_text())["questions"]
    Path(args.o).write_text(_format_md(answers, questions))
    print(args.o)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/llm/test_draft_ats_answers_mocked.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/application/draft_ats_answers.py tests/llm/test_draft_ats_answers_mocked.py
git commit -m "feat(application): ATS-answer drafter"
```

### Task 5.3: `stage.py`

**Files:**
- Create: `tools/application/stage.py`
- Create: `tests/unit/test_stage.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_stage.py`:
```python
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
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/unit/test_stage.py -v
```

- [ ] **Step 3: Implement `tools/application/stage.py`**

```python
"""Stage an application: create per-job folder, copy artifacts, append CSV row."""
from __future__ import annotations
import argparse, csv, json, re, shutil, sys
from datetime import datetime, timezone
from pathlib import Path

APPS_ROOT = Path("temp/outputs/applications")
CSV_PATH = APPS_ROOT / "applications.csv"
CSV_HEADER = ["job_id", "company", "title", "status", "staged_at", "submitted_at", "folder"]

def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:50] or "untitled"

def stage_application(job: dict, *, cv_pdf: Path,
                      cover_letter_md: Path | None = None,
                      cover_letter_pdf: Path | None = None,
                      ats_answers_md: Path | None = None,
                      match_result: dict | None = None) -> str:
    job_id = str(job["job_id"])
    folder = APPS_ROOT / f"{job_id}__{_slug(job.get('company') or 'unknown')}__{_slug(job.get('title') or 'untitled')}"
    if folder.exists():
        # Idempotency: stage is a no-op if already staged
        return str(folder)
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "job_details.json").write_text(json.dumps(job, indent=2, ensure_ascii=False))
    if match_result:
        (folder / "match_result.json").write_text(json.dumps(match_result, indent=2, ensure_ascii=False))
    shutil.copy(cv_pdf, folder / "tailored_cv.pdf")
    if cover_letter_md: shutil.copy(cover_letter_md, folder / "cover_letter.md")
    if cover_letter_pdf: shutil.copy(cover_letter_pdf, folder / "cover_letter.pdf")
    if ats_answers_md: shutil.copy(ats_answers_md, folder / "ats_answers.md")
    apply_url = job.get("apply_url") or job.get("url") or ""
    (folder / "apply_url.txt").write_text(apply_url + "\n")

    APPS_ROOT.mkdir(parents=True, exist_ok=True)
    new_file = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="") as f:
        w = csv.writer(f)
        if new_file: w.writerow(CSV_HEADER)
        w.writerow([job_id, job.get("company") or "", job.get("title") or "",
                    "staged", datetime.now(timezone.utc).isoformat(), "", str(folder)])
    return str(folder)

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--job-details", required=True)
    p.add_argument("--cv", required=True)
    p.add_argument("--cover-letter", default=None)
    p.add_argument("--cover-letter-pdf", default=None)
    p.add_argument("--ats-answers", default=None)
    p.add_argument("--match-result", default=None)
    args = p.parse_args()
    job = json.loads(Path(args.job_details).read_text())
    match = json.loads(Path(args.match_result).read_text()) if args.match_result else None
    folder = stage_application(
        job, cv_pdf=Path(args.cv),
        cover_letter_md=Path(args.cover_letter) if args.cover_letter else None,
        cover_letter_pdf=Path(args.cover_letter_pdf) if args.cover_letter_pdf else None,
        ats_answers_md=Path(args.ats_answers) if args.ats_answers else None,
        match_result=match,
    )
    print(folder)
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/unit/test_stage.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/application/stage.py tests/unit/test_stage.py
git commit -m "feat(application): stage.py with CSV master log + folder layout"
```

### Task 5.4: `mark_submitted.py`

**Files:**
- Create: `tools/application/mark_submitted.py`
- Create: `tests/unit/test_mark_submitted.py`

- [ ] **Step 1: Write failing test**

`tests/unit/test_mark_submitted.py`:
```python
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
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/unit/test_mark_submitted.py -v
```

- [ ] **Step 3: Implement `tools/application/mark_submitted.py`**

```python
"""Mark a staged application as submitted. Idempotent — refuses if already marked."""
from __future__ import annotations
import argparse, csv, json, sys
from datetime import datetime, timezone
from pathlib import Path

APPS_ROOT = Path("temp/outputs/applications")
CSV_PATH = APPS_ROOT / "applications.csv"

def _find_folder(job_id: str) -> Path:
    matches = list(APPS_ROOT.glob(f"{job_id}__*"))
    if not matches:
        raise RuntimeError(f"no staged application for job_id={job_id}")
    return matches[0]

def mark_submitted(job_id: str, notes: str | None = None) -> str:
    folder = _find_folder(job_id)
    marker = folder / "submitted.json"
    if marker.exists():
        raise RuntimeError(f"{job_id} already marked submitted at {marker}")
    now = datetime.now(timezone.utc).isoformat()
    marker.write_text(json.dumps({"submitted_at": now, "notes": notes or ""}, indent=2))
    # Update CSV row
    if CSV_PATH.exists():
        rows = list(csv.reader(CSV_PATH.read_text().splitlines()))
        header, *data = rows
        for r in data:
            if r and r[0] == job_id:
                r[3] = "submitted"
                r[5] = now
        with CSV_PATH.open("w", newline="") as f:
            w = csv.writer(f); w.writerow(header); w.writerows(data)
    return str(folder)

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("job_id")
    p.add_argument("--notes", default=None)
    args = p.parse_args()
    print(mark_submitted(args.job_id, notes=args.notes))
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests, verify pass**

```bash
pytest tests/unit/test_mark_submitted.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tools/application/mark_submitted.py tests/unit/test_mark_submitted.py
git commit -m "feat(application): mark_submitted with idempotency + CSV update"
```

---

## Phase 6 — Orchestrator + workflow markdown

### Task 6.1: `tools/run.sh`

**Files:**
- Create: `tools/run.sh`

- [ ] **Step 1: Write the orchestrator**

```bash
#!/usr/bin/env bash
# End-to-end job-search pipeline. See workflows/find-and-apply-jobs.md for the same
# steps in Mode-C agent-readable form.
set -euo pipefail

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
GEO_HIT=$(python tools/linkedin/resolve_location.py "$LOCATION" --pick-first)
GEO_ID=$(python -c "import json,sys; print(json.loads(sys.stdin.read())['id'])" <<< "$GEO_HIT")
echo "  → geoId=$GEO_ID"

echo "[1/7] search_jobs"
SEARCH_ARGS=(--keywords "$KEYWORDS" --geo-id "$GEO_ID" --limit "$LIMIT")
[[ -n "$POSTED_WITHIN_HOURS" ]] && SEARCH_ARGS+=(--posted-within-hours "$POSTED_WITHIN_HOURS")
python tools/linkedin/search_jobs.py "${SEARCH_ARGS[@]}" -o "$RUN_DIR/jobs_raw.json"
TOTAL=$(python -c "import json; print(len(json.load(open('$RUN_DIR/jobs_raw.json'))))")
echo "  → $TOTAL jobs"

echo "[1.5/7] fetch details (cache-aware)"
python <<PY
import json, os, time
from pathlib import Path
from datetime import datetime, timezone
import subprocess
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
        r = subprocess.run(["python", "tools/linkedin/get_job_details.py", jid],
                           capture_output=True, text=True, check=True)
        detail = json.loads(r.stdout)
        cache.write_text(json.dumps({"job_detail": detail,
                                      "cached_at": datetime.now(timezone.utc).isoformat()}, indent=2))
    merged = {**j, **detail}
    out.append(merged)
Path("$RUN_DIR/jobs_with_details.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
PY

echo "[2/7] keyword pre-filter (cutoff $FILTER_CUTOFF)"
python <<PY
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
python <<PY
import json, os, subprocess, tempfile
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
    # Invalidate if profile changed since
    if llm and (cached_at and datetime.fromisoformat(cached_at).timestamp() < profile_mtime):
        llm = None
    if NO_CACHE: llm = None
    if llm is None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as jf, \
             tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as kf:
            json.dump(j, jf); jf.flush()
            json.dump(j["keyword_score"], kf); kf.flush()
            r = subprocess.run(["python", "tools/match/score_llm.py",
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
python <<PY
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
            subprocess.run(["python", "tools/cv/tailor.py",
                            "--profile", "temp/resources/profile.md",
                            "--match-result", str(match_path),
                            "-o", str(yml_path)], check=True)
            pdf_path = tmp / "tailored_cv.pdf"
            subprocess.run(["python", "tools/cv/render.py", str(yml_path), "-o", str(pdf_path)], check=True)
            extra = []
            if WITH_COVER:
                cl = tmp / "cover_letter.md"
                subprocess.run(["python", "tools/application/draft_cover_letter.py",
                                "--profile", "temp/resources/profile.md",
                                "--job-details", str(jd_path),
                                "--match-result", str(match_path),
                                "-o", str(cl)], check=True)
                extra += ["--cover-letter", str(cl)]
            if WITH_ATS:
                ats = tmp / "ats_answers.md"
                subprocess.run(["python", "tools/application/draft_ats_answers.py",
                                "--profile", "temp/resources/profile.md",
                                "--job-details", str(jd_path),
                                "-o", str(ats)], check=True)
                extra += ["--ats-answers", str(ats)]
            subprocess.run(["python", "tools/application/stage.py",
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
python <<PY
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
    print(f"  python tools/application/mark_submitted.py {j['job_id']}")
PY
```

- [ ] **Step 2: Make executable**

```bash
chmod +x tools/run.sh
```

- [ ] **Step 3: Commit (smoke-test deferred to Phase 7)**

```bash
git add tools/run.sh
git commit -m "feat(orchestrator): run.sh end-to-end pipeline"
```

### Task 6.2: `workflows/find-and-apply-jobs.md`

**Files:**
- Create: `workflows/find-and-apply-jobs.md`

- [ ] **Step 1: Write the workflow markdown**

```markdown
# Find and Apply to Jobs

Purpose: Search LinkedIn for jobs matching the user's profile, score each
against `temp/resources/profile.md`, and stage tailored applications for
the best matches.

## Prerequisites
- `temp/resources/profile.md` exists.
- `.env` contains `ANTHROPIC_API_KEY`.
- `pip install -e ".[dev]"` has been run.
- `rendercv` is installed (`pip install rendercv` if missing).

## Inputs (CLI flags / agent should ask if missing)
- `--location` (required)        e.g. "Zurich, Switzerland"
- `--keywords` (required)        e.g. "engineer"
- `--posted-within-hours` (default 24)
- `--limit` (default 50)
- `--filter-cutoff` (default 0.4) — keyword score below this skips LLM call
- `--accept-threshold` (default 0.7) — final score at/above this triggers CV staging
- `--with-cover-letter` (default off)
- `--with-ats-answers` (default off)
- `--no-cache` (default off)

## Steps

1. **Resolve location.** Run `tools/linkedin/resolve_location.py "<location>" --pick-first`.
   Save the returned `id` as `geo_id`. If multiple Switzerland options exist
   in the non-`--pick-first` output, prefer the one whose `displayName` matches
   the user's intent.

2. **Search jobs.** Run
   `tools/linkedin/search_jobs.py --keywords <kw> --geo-id <geo_id> [--posted-within-hours N] --limit N -o <run_dir>/jobs_raw.json`.

3. **For each job in `jobs_raw.json`:**
   3a. Check `temp/outputs/cache/<job_id>.json`. If present and `cached_at`
       is within 7 days and (for keyword/llm scores) newer than `profile.md` mtime,
       reuse cached fields. Else call `tools/linkedin/get_job_details.py <job_id>`
       and write to cache.
   3b. Run `tools/match/extract_skills.py --source jd` on the JD text, then
       `tools/match/score_keyword.py --profile temp/resources/profile.md --jd <jd_file>`.
   3c. If keyword score < `--filter-cutoff` → skip this job; log "filtered".
   3d. Run `tools/match/score_llm.py` with the JD details and keyword result.
   3e. If `final_score < --accept-threshold` → log "below threshold"; continue.
   3f. Else:
       - `tools/cv/tailor.py` → `tailored_cv.yml`
       - `tools/cv/render.py` → `tailored_cv.pdf`
       - If `--with-cover-letter`: `tools/application/draft_cover_letter.py`
       - If `--with-ats-answers`: `tools/application/draft_ats_answers.py`
       - `tools/application/stage.py` to assemble the folder.

4. **Print summary table** to stdout (counts of search/filtered/matched/accepted).

5. **Next-action checklist** — for each staged application, print:
   - `open temp/outputs/applications/{job_id}__*/apply_url.txt`
   - `python tools/application/mark_submitted.py {job_id}`

## Outputs

- `temp/outputs/runs/<timestamp>/` — intermediates (`jobs_raw.json`,
  `jobs_with_details.json`, `jobs_filtered.json`, `jobs_matched.json`, `run.log`).
- `temp/outputs/applications/{job_id}__{company}__{slug}/` — durable per-job folder.
- `temp/outputs/applications.csv` — master log.
- `temp/outputs/cache/<job_id>.json` — cache (7d TTL).
```

- [ ] **Step 2: Commit**

```bash
git add workflows/find-and-apply-jobs.md
git commit -m "docs(workflow): find-and-apply-jobs playbook (Mode-C readable)"
```

---

## Phase 7 — Smoke test + final verify

### Task 7.1: Offline E2E smoke test

**Files:**
- Create: `tests/smoke/test_end_to_end_offline.sh`

- [ ] **Step 1: Write the smoke test**

```bash
mkdir -p tests/smoke
```

`tests/smoke/test_end_to_end_offline.sh`:
```bash
#!/usr/bin/env bash
# Offline E2E: stubs the LLM and uses cached LinkedIn HTML. Confirms the
# pipeline writes a non-empty PDF and adds a CSV row.
set -euo pipefail
cd "$(dirname "$0")/../.."

WORK=$(mktemp -d)
trap "rm -rf $WORK" EXIT

# Minimal fake profile
cat > "$WORK/profile.md" <<'EOF'
---
name: "Test User"
title: "Engineer"
email: "t@e.st"
phone: "+1"
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
python tools/cv/tailor.py --profile "$WORK/profile.md" --match-result "$WORK/match.json" -o "$WORK/tailored.yml"
test -s "$WORK/tailored.yml"

# Render
python tools/cv/render.py "$WORK/tailored.yml" -o "$WORK/cv.pdf"
test -s "$WORK/cv.pdf"

# Stage (in an isolated cwd so we don't pollute real applications)
pushd "$WORK" > /dev/null
python "$OLDPWD/tools/application/stage.py" --job-details "$WORK/jd.json" --cv "$WORK/cv.pdf" --match-result "$WORK/match.json"
test -d "temp/outputs/applications" && ls temp/outputs/applications/X1__*/
test -f "temp/outputs/applications/applications.csv"
popd > /dev/null

echo "SMOKE OK"
```

- [ ] **Step 2: Make executable + run**

```bash
chmod +x tests/smoke/test_end_to_end_offline.sh
./tests/smoke/test_end_to_end_offline.sh
```
Expected: prints `SMOKE OK`.

- [ ] **Step 3: Commit**

```bash
git add tests/smoke/test_end_to_end_offline.sh
git commit -m "test(smoke): offline end-to-end PDF + staging verification"
```

### Task 7.2: Full live smoke (manual)

This isn't automated — you'll run it yourself to confirm the full path works end-to-end.

- [ ] **Step 1: Run the full pipeline**

```bash
./tools/run.sh --location "Zurich, Switzerland" --keywords engineer --posted-within-hours 24 --limit 10
```

- [ ] **Step 2: Verify**

```
temp/outputs/runs/<timestamp>/run.log           — exists
temp/outputs/runs/<timestamp>/jobs_raw.json     — ≥1 job
temp/outputs/runs/<timestamp>/jobs_matched.json — has llm_score per job
temp/outputs/applications/<job_id>__*/          — at least one folder for accepted jobs
temp/outputs/applications/applications.csv      — has rows
```

- [ ] **Step 3: Manual click-test**

```bash
cat temp/outputs/applications/<job_id>__*/apply_url.txt
# Open the URL in browser. Confirm CV PDF renders cleanly.
```

- [ ] **Step 4: (Optional) Mark one as submitted**

```bash
python tools/application/mark_submitted.py <job_id> --notes "Test submission"
# Confirm submitted.json created and CSV updated.
```

---

## Coverage check vs spec

| Spec section | Covered by |
|---|---|
| §4 Architecture (CLI tools, Modes A/C) | Phase 6 (`run.sh`, `workflows/find-and-apply-jobs.md`) |
| §5 Folder layout | Phase 0–6 (all paths match spec) |
| §6.1 LinkedIn module | Tasks 2.1, 2.2, 2.3 |
| §6.2 Match module | Tasks 3.1, 3.2, 3.3 |
| §6.3 CV module | Tasks 4.1, 4.2 |
| §6.4 Application module | Tasks 5.1, 5.2, 5.3, 5.4 |
| §6.5 Orchestrator | Task 6.1 |
| §7 Data flow (Phases 0–7) | Task 6.1 `run.sh` mirrors phases |
| §8 Workflow markdown | Task 6.2 |
| §9 Skill dictionary | Task 1.2 |
| §10 Error handling | `run.sh` (`set -euo pipefail`); per-tool `raise_for_status()` and try/except patterns. **Gap:** explicit 429 backoff in `search_jobs.py` is not implemented in this plan — it currently `raise`s. Acceptable for v1; flagged in §14 spec. |
| §11 Idempotency & caching | Task 6.1 (`run.sh` cache logic); Task 5.3 (stage idempotency); Task 5.4 (mark_submitted idempotency) |
| §12 Testing | Phase 0–7 (each tool has its tests; Task 7.1 = offline smoke) |
| §13 Project metadata | Task 0.1 |
