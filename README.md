# WAT Job Search

Automated LinkedIn job research with tailored CV generation. Runs from
Claude Desktop in this directory — no command-line orchestrator.

## Install
```bash
pip install -e ".[dev]"
cp .env.example .env  # add your ANTHROPIC_API_KEY
```

## Use

Open this directory in Claude Desktop and ask:
> *"Find me jobs in Zurich matching 'ai OR software developer OR consultant', posted in the last 72 hours, and generate tailored CVs for the strong matches."*

Claude reads [workflows/find-and-apply-jobs.md](workflows/find-and-apply-jobs.md)
and orchestrates the individual tools step by step.

## Dashboard

```bash
python -m tools.server
```

Then open [http://localhost:8765](http://localhost:8765) — a three-column dashboard
(NEW / VIEWED / STAGED) backed by SQLite at `temp/outputs/jobs.db`. Click
**Generate PDF** on a job that already has an LLM match score to trigger
the tailor + render pipeline; the resulting CV is opened in a new tab.

## Where artifacts go

- `temp/outputs/runs/<timestamp>/` — per-run intermediates (search results,
  JD details, keyword scores, LLM match results, run log).
- `temp/outputs/applications/{job_id}__.../` — durable per-job artifacts
  (tailored CV PDF with preserved source header, match analysis, apply URL).
- `temp/outputs/applications.csv` — master log: which jobs were staged, when,
  and which have been marked as submitted.

## Tests

```bash
pytest tests/
```

## Tools (called by Claude)

```
tools/linkedin/   → resolve_location, search_jobs, get_job_details
tools/match/      → extract_skills, score_keyword, score_llm
tools/cv/         → tailor, render_body_weasy, render_with_source_header
tools/application/→ draft_cover_letter, draft_ats_answers, stage, mark_submitted
tools/shared/     → http (curl_cffi + Chrome impersonation), skill_dictionary.yml,
                    ats_questions.yml, prompts/*.md
```
