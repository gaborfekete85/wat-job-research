# Design Spec — LinkedIn Job Research & Tailored Application Workflow

**Date:** 2026-06-10
**Status:** Approved (ready for implementation plan)
**Author:** Gabor Fekete (with Claude Code)
**Target framework:** WAT (Workflows · Agent · Tools), per project `CLAUDE.md`

---

## 1. Summary

A personal job-search automation built on the WAT framework. Given a location and keywords, it:

1. Searches LinkedIn's public job pages (no login, no API key, no scraping API).
2. Pre-filters jobs with a deterministic keyword overlap against the user's `profile.md`.
3. Scores surviving jobs with a single Claude API call that also produces a tailoring plan.
4. Generates a job-specific tailored CV PDF via `rendercv` for jobs that pass the acceptance threshold.
5. Stages each application (CV + optional cover letter + optional ATS-answers draft + apply URL) in a per-job folder for human review and click-to-submit.

No automated submission. No browser automation. No LinkedIn ToS violation beyond reading public-page HTML.

## 2. Goals

- End-to-end run completes in ~3 minutes for a typical Zurich-engineer search (~50 jobs).
- Per-run LLM cost in the cents range (~$0.18 for the example above).
- Zero state outside `temp/` — fully reproducible reruns.
- Same tooling supports two execution modes:
  - **Mode A:** single CLI invocation (`./tools/run.sh ...`) for hands-off batch runs.
  - **Mode C:** agentic — Claude in this directory reads the workflow markdown and orchestrates the same tools conversationally.

## 3. Non-goals (out of scope for v1)

- Alternative job sources (JSearch, Adzuna, Indeed, etc.).
- MCP-server wrapping of LinkedIn (CLI tools only for v1; can be added later without rewriting the workflow).
- LinkedIn Easy Apply auto-submission (prepare-and-stage only).
- Per-ATS submission adapters (Greenhouse, Workday, etc.).
- Multi-location runs in a single invocation.
- Recruiter outreach / cold messaging.
- Interview tracking post-application.

## 4. Architecture

Pure CLI tools orchestrated by either a bash script (Mode A) or by the agent reading the workflow markdown (Mode C). All tools are stateless, single-purpose, exit cleanly, and write JSON to stdout or a path passed via `-o`. The workflow markdown and `run.sh` mirror each other step-for-step — drift between them is a bug.

LLM calls are limited to three places:
- `score_llm.py` (one call per surviving job)
- `draft_cover_letter.py` (only when `--with-cover-letter` is set)
- `draft_ats_answers.py` (only when `--with-ats-answers` is set)

All other transformations are deterministic Python.

## 5. Folder layout

```
job-search/
├── CLAUDE.md                            # WAT config (already exists)
├── README.md                            # Quick start (40 lines)
├── .env.example                         # ANTHROPIC_API_KEY=...
├── .gitignore                           # already exists
├── pyproject.toml                       # deps pinned to majors
│
├── docs/
│   └── specs/
│       └── 2026-06-10-job-search-workflow-design.md   # this file
│
├── workflows/
│   └── find-and-apply-jobs.md           # playbook (humans + agent)
│
├── tools/
│   ├── run.sh                           # Mode A orchestrator
│   ├── linkedin/
│   │   ├── resolve_location.py
│   │   ├── search_jobs.py
│   │   └── get_job_details.py
│   ├── match/
│   │   ├── extract_skills.py
│   │   ├── score_keyword.py
│   │   └── score_llm.py
│   ├── cv/
│   │   ├── tailor.py
│   │   └── render.py
│   ├── application/
│   │   ├── draft_cover_letter.py
│   │   ├── draft_ats_answers.py
│   │   ├── stage.py
│   │   └── mark_submitted.py
│   └── shared/
│       ├── skill_dictionary.yml         # ~150 canonical terms + synonyms
│       ├── ats_questions.yml            # common Qs to draft answers for
│       ├── prompts/
│       │   ├── match_score.md
│       │   ├── cover_letter.md
│       │   └── ats_answers.md
│       └── http.py                      # requests wrapper w/ UA + throttle
│
├── tests/
│   ├── unit/                            # pytest, no network, no LLM
│   ├── parsers/                         # snapshot tests against captured HTML
│   │   └── fixtures/
│   └── smoke/                           # one offline E2E
│
└── temp/
    ├── resources/
    │   └── profile.md                   # already exists
    └── outputs/
        ├── cache/                       # per-job cache, 7-day TTL
        ├── runs/                        # per-run intermediates
        │   └── 2026-06-10T12-30/
        │       ├── run.log
        │       ├── jobs_raw.json
        │       ├── jobs_filtered.json
        │       └── jobs_matched.json
        └── applications/
            ├── applications.csv          # master log
            └── {job_id}__{company}__{slug}/
                ├── job_details.json
                ├── match_result.json
                ├── tailored_cv.yml
                ├── tailored_cv.pdf
                ├── cover_letter.md       # optional
                ├── cover_letter.pdf      # optional
                ├── ats_answers.md        # optional
                ├── apply_url.txt
                └── submitted.json        # created by mark_submitted.py
```

## 6. Tool surface

Each tool: purpose, CLI usage, JSON output shape.

### 6.1 LinkedIn module

```
resolve_location.py "Zurich, Switzerland" [--pick-first]
  Wraps: GET /jobs-guest/api/typeaheadHits?typeaheadType=GEO&query=...
  Output: [{"id":"107814425","displayName":"Zurich, Zurich, Switzerland"}, ...]

search_jobs.py --keywords <str> --geo-id <str>
               [--posted-within-hours <int>] [--limit <int>] [-o <path>]
  Wraps: GET /jobs-guest/jobs/api/seeMoreJobPostings/search?...
  Paginates by 25 with 1.5s throttle.
  Output: [JobSummary] where JobSummary =
    {job_id, title, company, location, posted, url}

get_job_details.py <job_id> [-o <path>]
  Wraps: GET /jobs-guest/jobs/api/jobPosting/{job_id}
  Output: JobDetail = JobSummary + 
    {description, seniority, employment_type, job_function, industry, apply_url}
```

### 6.2 Match module

```
extract_skills.py --source profile|jd --input <path-or-stdin>
  Uses shared/skill_dictionary.yml for canonicalization + synonyms.
  Case-insensitive, word-boundary aware.
  Output: {"skills": ["AWS", "Kubernetes", "Spring", ...]}

score_keyword.py --profile profile.md --jd jd.txt
  score = |jd_skills ∩ profile_skills| / |jd_skills|
  Output: {"score": 0.62, "matched": [...], "missing": [...], "jd_skills": [...]}

score_llm.py --profile profile.md --job-details job.json
             --keyword-result keyword_score.json
  Single Claude API call. Prompt at shared/prompts/match_score.md.
  Strict JSON response via tool-use schema.
  Output: {
    "final_score": 0.0..1.0,
    "skills_match": 0.0..1.0,
    "seniority_fit": "below"|"fit"|"above",
    "location_fit": bool,
    "matched_skills": [str],
    "missing_critical": [str],
    "reasoning": str,
    "suggested_emphasis": {
      "tailored_summary": str,
      "priority_skills": [str],
      "priority_experiences": [int],         # indices into profile.experience
      "priority_bullets": {<exp_idx>: [int]} # indices into highlights[]
    }
  }
```

### 6.3 CV module

```
tailor.py --profile profile.md --match-result match.json -o tailored_cv.yml
  Pure transformation (NO LLM call — uses suggested_emphasis from match).
  - Replaces summary with tailored_summary
  - Reorders skills to lead with priority_skills
  - For each experience: keeps highlights at indices priority_bullets[i]
  Output: rendercv-formatted YAML written to -o; path printed to stdout.

render.py <tailored_cv.yml> -o <tailored_cv.pdf> [--theme <name>]
  Thin wrapper: rendercv render <yml> --output-folder ...
  Default theme: engineeringresumes
```

### 6.4 Application module

```
draft_cover_letter.py --profile profile.md --job-details job.json
                      --match-result match.json -o cover_letter.md
  Single Claude API call. Prompt at shared/prompts/cover_letter.md.
  Conservative — uses only facts present in profile.md.
  Also writes cover_letter.pdf via rendercv. KNOWN ISSUE: rendercv is
  CV-shaped, so the PDF styling for a cover letter is a rough first pass
  — flagged in §14 for a dedicated v2 template.

draft_ats_answers.py --profile profile.md --job-details job.json
                     -o ats_answers.md
  Single Claude API call. Reads common questions from shared/ats_questions.yml.
  Output: markdown with Q&A pairs for the user to edit before submitting.

stage.py --job-details job.json --cv tailored_cv.pdf
         [--cover-letter cover_letter.md] [--ats-answers ats_answers.md]
  Creates temp/outputs/applications/{job_id}__{company}__{slug}/
  Copies artifacts in, writes apply_url.txt extracted from job_details.apply_url.
  Appends row to applications.csv with status="staged".
  Output: absolute path to the application folder.

mark_submitted.py <job_id> [--notes "..."]
  Idempotent — refuses if submitted.json already exists in the folder.
  Writes submitted.json (timestamp + notes), updates the CSV row status.
```

### 6.5 Orchestrator

```
run.sh --location "<str>" --keywords "<str>"
       [--filter-cutoff 0.4] [--accept-threshold 0.7]
       [--posted-within-hours 24] [--limit 50]
       [--with-cover-letter] [--with-ats-answers]
       [--no-cache]
  Runs the full pipeline (Phases 0-7 below). Prints summary table.
```

## 7. End-to-end data flow

```
Phase 0  Setup
         - mkdir temp/outputs/runs/<timestamp>/
         - resolve_location.py → geo_id (1 HTTP call)

Phase 1  Search (zero LLM, ~75s for limit=50)
         - search_jobs.py → jobs_raw.json
         - For each: get_job_details.py (cache-aware)
         - Throttle: 1.5s between LinkedIn calls

Phase 2  Keyword pre-filter (zero LLM, <2s)
         - extract_skills.py + score_keyword.py per job
         - Drop jobs where score < --filter-cutoff
         - Write jobs_filtered.json

Phase 3  LLM scoring (~$0.01/job, ~30s for 18 survivors)
         - score_llm.py per survivor
         - Write jobs_matched.json (all survivors with final_score)

Phase 4  Tailoring + render (zero LLM, ~3s/job)
         - For each job with final_score >= --accept-threshold:
           - tailor.py → tailored_cv.yml
           - render.py → tailored_cv.pdf

Phase 5  Optional artifacts (only if flags set)
         - draft_cover_letter.py
         - draft_ats_answers.py

Phase 6  Staging
         - stage.py per accepted job → application folder
         - Append to applications.csv

Phase 7  Summary
         - Print table of search / filtered / matched / accepted counts
         - Print next-action checklist (apply_url + mark_submitted command)
```

**Single-run budget (Zurich, last 24h, engineer, limit 50):**

| Phase | Time | Cost |
|---|---|---|
| Search + details | ~75 s | $0 |
| Keyword pre-filter | <2 s | $0 |
| LLM scoring (~18 jobs) | ~30 s | ~$0.18 |
| CV render (6 jobs) | ~20 s | $0 |
| **Total** | **~3 min** | **~$0.18** |

## 8. Workflow markdown

`workflows/find-and-apply-jobs.md` — readable by humans and by the agent in Mode C. Structure:

- **Purpose** (1 sentence)
- **Prerequisites** (profile.md, .env, deps)
- **Inputs** (CLI flags / what the agent should ask)
- **Steps** (numbered, each naming the tool to call and what to do with the output)
- **Outputs** (where artifacts land)

The file mirrors `run.sh` step-for-step. The format is "numbered steps with tool calls" — see Section 4 of the brainstorming transcript for the prototype.

## 9. Skill dictionary

`tools/shared/skill_dictionary.yml` — ~150 canonical terms + synonyms.

Format:

```yaml
languages:
  Java: [java]
  Python: [python, py]
  # ...
frameworks:
  Spring: [spring, "spring boot", "spring framework"]
  # ...
cloud_devops:
  AWS: [aws, "amazon web services", ec2, ecs, s3, rds, vpc, cloudwatch]
  Kubernetes: [kubernetes, k8s]
  # ...
```

**Design choices:**
- AWS sub-services (ec2, ecs, s3, etc.) collapsed under canonical `AWS` — recruiters search on the umbrella term. Sub-service hits still recorded in matched output, no information loss.
- Categories preserved so future weighting (e.g., languages > soft skills) is possible without restructuring.
- Conservative synonyms only — false positives avoided by word-boundary regex; semantic gaps caught by the LLM scorer.

Seed sourced from: `profile.md` (everything under `skills:`) + common CH/EU tech-job vocabulary.

## 10. Error handling

| Failure | Behavior |
|---|---|
| Missing `profile.md`, missing API key, invalid CLI args | Fail fast, exit 1, run never starts |
| Per-job HTTP / parse / LLM / rendercv failure | Log + skip that job, continue. Recorded in `run.log` |
| LinkedIn 429 (first occurrence) | Throttle 1.5s → 5s for rest of run, retry once after 30s pause |
| LinkedIn 429 (second occurrence) | Abort with explanatory message; partial results preserved |
| HTML parse failure | Save offending HTML to `runs/<ts>/parse_failures/{job_id}.html` |
| rendercv failure | Save offending YAML to `runs/<ts>/render_failures/{job_id}/`. Skip CV → application NOT staged |
| >50% of jobs in a run fail | Abort, print "something's structurally wrong" |

## 11. Idempotency & caching

- `temp/outputs/cache/{job_id}.json` stores `{job_detail, keyword_score, llm_score, cached_at}`.
- Each phase checks for and reuses cached fields independently:
  - Phase 1 reuses `job_detail` if present (skips HTTP call).
  - Phase 2 reuses `keyword_score` if present and `profile.md` mtime is older than `cached_at`.
  - Phase 3 reuses `llm_score` under the same `profile.md`-mtime condition.
- Cache TTL: 7 days. Reset all with `--no-cache`.
- Stage step skips any `job_id` already present in `applications.csv` — no re-staging.

## 12. Testing

```
tests/unit/                              # pytest, no network, no LLM
  test_extract_skills.py                 # synonyms, word boundaries, case
  test_score_keyword.py                  # known pairs → known scores
  test_skill_dictionary.py               # YAML structural validity
  test_resolve_location.py               # uses saved typeahead fixture

tests/parsers/                           # against captured HTML fixtures
  fixtures/linkedin_search_page__zurich.html
  fixtures/linkedin_job_detail__4417627058.html
  test_html_parsers.py                   # snapshot-style: HTML in → JSON out

tests/smoke/
  test_end_to_end_offline.sh             # canned JDs + mocked LLM; verifies
                                         #   the orchestrator chains correctly
                                         #   and produces a non-empty PDF
```

No tests against live LinkedIn or live Claude — flaky and costly.

## 13. Project metadata

**`pyproject.toml`:**

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

[tool.ruff]
line-length = 100
```

**`.env.example`:**

```
ANTHROPIC_API_KEY=
# Optional:
# CLAUDE_MODEL=claude-sonnet-4-6
# LINKEDIN_USER_AGENT=...
```

## 14. Open items / future work

Not blockers — call out for v2 conversation:

- **Cover letter PDF rendering** — currently we generate a `.md` and emit a `.pdf` via rendercv. rendercv is CV-shaped, so cover-letter PDF rendering is the rough edge. May want a dedicated template (e.g., Typst directly or a simple WeasyPrint pass).
- **HTML parser brittleness** — LinkedIn changes their DOM occasionally. Mitigation in place (parse_failures dump + fixture-based tests), but a real change will require manual selector updates.
- **MCP-wrapped LinkedIn** — interesting v2 upgrade, makes the search/details tools callable from any Claude session. Not needed for the workflow itself.
- **JSearch / Adzuna fallback** — would diversify if LinkedIn blocks the IP. Same `JobSummary` shape, drop-in replacement for `search_jobs.py`.

---

## Appendix A — Confirmed decisions (this brainstorming session)

| # | Decision | Choice |
|---|---|---|
| 1 | Data source | LinkedIn public guest endpoints |
| 2 | Matching | Keyword pre-filter + LLM scorer on survivors |
| 3 | Pre-filter cutoff | Configurable, default 0.4 |
| 4 | CV rendering | rendercv (Typst-based, YAML-driven) |
| 5 | Submission | Prepare & stage — no auto-submit |
| 6 | Tool packaging | Pure CLI scripts; MCP wrapping deferred |
| 7 | Execution modes | Mode A (run.sh) + Mode C (agent reads workflow.md) |
| 8 | LinkedIn throttle | Fixed 1.5s |
| 9 | Cover letter / ATS answers | Default OFF, opt-in flags |
| 10 | Workflow markdown style | Numbered steps with tool calls |
| 11 | Skill dictionary scope | ~150 entries seeded from profile + common terms |
| 12 | Per-job error policy | Log + continue (abort only if >50% fail) |
| 13 | Live LLM/LinkedIn tests | None — offline fixtures only |
