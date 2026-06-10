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

## Scheduling — run the backfill automatically every hour

The recommended path is a **local launchd agent on macOS**. The remote-routine
system in Claude Code (see "Alternatives" below) doesn't fit because this
project's state (SQLite DB, cache, dashboard) lives on your laptop — a cloud
sandbox can't reach any of it.

### One-time setup (macOS)

1. **The wrapper script is already in the repo:** [`scripts/collect-jobs-hourly.sh`](scripts/collect-jobs-hourly.sh).
   It `cd`s to the project root, sources `.env`, and runs
   `python -m tools.workflow.search "$@"` — logging to `temp/outputs/launchd.log`.

   Make sure it's executable:
   ```bash
   chmod +x scripts/collect-jobs-hourly.sh
   ```

2. **Create the launchd plist.** Open `~/Library/LaunchAgents/com.feketegabor.wat-collect-jobs.plist`
   and paste:

   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
     "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
       <key>Label</key>
       <string>com.feketegabor.wat-collect-jobs</string>

       <key>ProgramArguments</key>
       <array>
           <string>/bin/bash</string>
           <string>/Users/gaborfekete/my-projects/my-agent/wat-frameworks/job-search/scripts/collect-jobs-hourly.sh</string>
       </array>

       <!-- Fire every 3600 seconds = 1 hour while the laptop is awake.
            If the laptop is asleep at the scheduled tick, launchd will fire
            once on wake instead of catching up multiple times. -->
       <key>StartInterval</key>
       <integer>3600</integer>

       <!-- Don't run on plist load — the user runs it manually first to
            confirm the wrapper works, then trusts the hourly cadence. -->
       <key>RunAtLoad</key>
       <false/>

       <key>StandardOutPath</key>
       <string>/Users/gaborfekete/my-projects/my-agent/wat-frameworks/job-search/temp/outputs/launchd.out.log</string>

       <key>StandardErrorPath</key>
       <string>/Users/gaborfekete/my-projects/my-agent/wat-frameworks/job-search/temp/outputs/launchd.err.log</string>
   </dict>
   </plist>
   ```

   Replace the absolute paths if your project lives somewhere else.

3. **Load it:**
   ```bash
   launchctl load ~/Library/LaunchAgents/com.feketegabor.wat-collect-jobs.plist
   ```

4. **Sanity-test it once, manually:**
   ```bash
   launchctl start com.feketegabor.wat-collect-jobs
   tail -f temp/outputs/launchd.log
   ```
   You should see a `/collect-jobs` block appended, ending with the stats line.

### Managing the schedule

```bash
# Confirm it's loaded (look for the Label in the output)
launchctl list | grep wat-collect-jobs

# Fire it on demand
launchctl start com.feketegabor.wat-collect-jobs

# Live-tail the rolling log
tail -f temp/outputs/launchd.log

# Stop it temporarily (unload — survives until you reload)
launchctl unload ~/Library/LaunchAgents/com.feketegabor.wat-collect-jobs.plist

# Re-arm it
launchctl load ~/Library/LaunchAgents/com.feketegabor.wat-collect-jobs.plist

# Change the cadence: edit StartInterval (seconds) in the plist, then
# unload + load again to pick up the change.
```

### What happens on each run

1. Wrapper sources `.env` and `cd`s to the project root.
2. `python -m tools.workflow.search` runs with the **saved DB preferences**
   (`keywords`, `location`, `location_geo_id`) and **default threshold 0.5**.
3. New jobs land in NEW (or FILTERED_OUT for below-threshold). Existing job IDs
   are skipped untouched — your triage state survives every run.
4. The dashboard at `http://localhost:8765` auto-refreshes every 5 seconds, so
   new rows appear without a manual reload.

Cost per run: **$0** (the backfill is pure regex + arithmetic; no Anthropic API).
Typical wall-clock: 1–4 minutes depending on cache hits.

### Alternatives (and why they don't fit as cleanly)

| Option | When it makes sense | Why we didn't pick it |
|---|---|---|
| **Claude Code remote routine** (`/schedule`) | Project state lives in cloud (GitHub, hosted DB, public APIs). | Remote sandbox can't reach our local SQLite, local cache, or `localhost:8765`. |
| **`/loop /collect-jobs 1h`** | You keep a Claude session open all day anyway. | Stops the moment the Claude session closes. |
| **`crontab -e` with `0 * * * *`** | Linux server, or you prefer the classic cron syntax. | Equivalent to launchd on macOS — just less native. Pick whichever you're more comfortable maintaining. |

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




Warmup: 
```
.venv/bin/python -m tools.workflow.search --days 4 --threshold 0.7
```