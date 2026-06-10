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

A three-column dashboard (NEW / VIEWED / STAGED) backed by SQLite at
`temp/outputs/jobs.db`. Click **Generate PDF** on a job that already has an LLM
match score to trigger the tailor + render pipeline; the resulting CV opens
in a new tab. Jobs persist across runs — what you see today will still be
there tomorrow with the same statuses.

### Start the server

From the project root, with the venv:

```bash
.venv/bin/python -m tools.server
```

Then open **[http://localhost:8765](http://localhost:8765)** in your browser.

The default port is 8765; override with `--port`:
```bash
.venv/bin/python -m tools.server --port 9000
```

### Run it in the background (so you don't have to keep the terminal open)

```bash
nohup .venv/bin/python -m tools.server > temp/outputs/server.log 2>&1 &
echo $! > temp/outputs/server.pid     # remember the PID so we can stop it later
```

Stop it:
```bash
kill "$(cat temp/outputs/server.pid)" && rm temp/outputs/server.pid
```

Live-tail the log while it's running:
```bash
tail -f temp/outputs/server.log
```

### "I see empty columns — nothing is showing up"

The dashboard reads the SQLite DB. If you haven't run a search yet, the DB has
no rows. Two paths to populate it:

- **Most common:** ask Claude Desktop in this directory to run the workflow
  (e.g. *"Find me jobs in Zurich matching 'ai OR software developer'"*). The
  workflow runs the LinkedIn pipeline and calls `python -m tools.db.ingest`
  to seed the DB.
- **Manual ingest** of an existing run:
  ```bash
  .venv/bin/python -m tools.db.ingest \
      --jobs temp/outputs/runs/<timestamp>/jobs_filtered.json
  ```

After ingesting, refresh the browser tab — the new jobs show up in the NEW
column.

### Server-side API (Claude can call these too)

| Endpoint | Use |
|---|---|
| `GET /api/jobs` | list new/viewed/staged/submitted buckets |
| `GET /api/jobs/{id}` | full row including JD and LLM match result |
| `POST /api/jobs/{id}/view` | mark a job as VIEWED |
| `POST /api/jobs/{id}/dismiss` | hide a job |
| `POST /api/jobs/{id}/generate-pdf` | kick off tailor+render (refuses 409 if no LLM score yet) |
| `GET /api/jobs/{id}/pdf-status` | poll PDF render progress (`idle` / `running` / `done` / `error:…`) |
| `GET /pdfs/{id}.pdf` | download the staged tailored CV |

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
