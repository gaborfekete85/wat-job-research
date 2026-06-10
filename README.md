# WAT Job Research

Automated LinkedIn job research with tailored CV generation. Runs from
Claude Desktop in this directory — no command-line orchestrator.

## One-line install

```bash
curl -fsSL https://raw.githubusercontent.com/gaborfekete85/wat-job-research/main/install.sh | bash
```

The installer:
- clones the repo to `$HOME/wat-job-research` (override with `WAT_INSTALL_DIR=…`)
- creates `.venv` with Python 3.11+
- `pip install -e ".[dev]"`
- seeds `.env` (placeholder API key) and `profile/profile.md` (CV template
  from `profile/profile.md.example`) — neither is overwritten on re-run
- smoke-tests every Python import

Idempotent — re-run any time to pull `main` and reinstall deps.

### Manual install (if you'd rather not pipe curl into bash)

```bash
git clone https://github.com/gaborfekete85/wat-job-research.git
cd wat-job-research
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                                # add your ANTHROPIC_API_KEY (optional)
cp profile/profile.md.example profile/profile.md    # edit with your CV
cp ~/Downloads/your-cv.pdf profile/cv_source.pdf    # your existing CV PDF (header is preserved)
```

## Your profile (crucial — every step reads from here)

Everything in this project — keyword matching, JD scoring, CV tailoring,
cover letter drafting — reads from a **single source of truth**:

```
profile/
  ├── profile.md.example   ← starter template (tracked in git)
  ├── README.md            ← how-to (tracked)
  ├── profile.md           ← YOUR CV in YAML + free text (gitignored)
  └── cv_source.pdf        ← YOUR existing CV PDF — its header (QR codes /
                              photo / contact / LinkedIn icon) is preserved
                              on every tailored CV. (gitignored)
```

Both `profile.md` and `cv_source.pdf` are gitignored by default so they
never accidentally leak into a public fork. If you want them to follow
you across machines via your **private** fork, `git add -f` them
intentionally.

See [profile/README.md](profile/README.md) for details.

## Use

Open this directory in Claude Desktop and ask:
> *"Find me jobs in Zurich matching 'ai OR software developer OR consultant', posted in the last 72 hours, and generate tailored CVs for the strong matches."*

Claude reads [workflows/find-and-apply-jobs.md](workflows/find-and-apply-jobs.md)
and orchestrates the individual tools step by step.

## Dashboard

A persistent dashboard (NEW / VIEWED / STAGED / SUBMITTED / FILTERED OUT)
backed by SQLite at `temp/outputs/jobs.db`. Drag cards between columns to
triage, click **Generate PDF** on a job with an LLM score to trigger the
tailor+render pipeline, and drag to SUBMITTED once you've actually applied.
Jobs persist across runs — what you see today will still be there tomorrow
with the same statuses.

### Start the server

```bash
.venv/bin/python -m tools.server
```

Then open **[http://localhost:8765](http://localhost:8765)** in your browser.
The default port is 8765; override with `--port 9000` if needed.

### Run it in the background

```bash
nohup .venv/bin/python -m tools.server > temp/outputs/server.log 2>&1 &
echo $! > temp/outputs/server.pid

# stop it later
kill "$(cat temp/outputs/server.pid)" && rm temp/outputs/server.pid

# follow the log
tail -f temp/outputs/server.log
```

### Empty columns?

The dashboard reads SQLite. Until you've run a search, the DB has no rows.
Easiest fix: open this dir in Claude Desktop and run `/collect-jobs` — see
the next section.

## Two slash commands you'll use most

Both are project-local — they're available the moment you open this
directory in Claude Desktop.

| Slash command | What it does |
|---|---|
| `/collect-jobs [--days N] [--threshold 0.5]` | Run one backfill (paginated LinkedIn search → keyword score → dedup insert). Claude reports the diff (NEW vs FILTERED OUT vs skipped). |
| `/schedule-collect [install \| remove \| status]` | Install (or remove, or check) a macOS launchd agent that fires `/collect-jobs` every hour while the laptop is awake. No remote infrastructure; nothing to push. |

**Hourly auto-collection in three messages:**

> *"/schedule-collect install"* — Claude writes `~/Library/LaunchAgents/com.${USER}.wat-collect-jobs.plist`, loads it via launchctl, fires it once as a smoke test, and reports what it did.
>
> *"/schedule-collect status"* — confirms it's still loaded and shows the last few runs from `temp/outputs/launchd.log`.
>
> *"/schedule-collect remove"* — unloads and deletes the plist when you don't need it anymore.

Both commands use **zero Anthropic API credits** by default — the backfill
itself is pure deterministic regex + arithmetic (see
[`tools/workflow/search.py`](tools/workflow/search.py) for the entire
~200-line orchestrator).

## Where artifacts go

| Path | What's there |
|---|---|
| `profile/profile.md` | Your CV in YAML — the matcher reads this. |
| `profile/cv_source.pdf` | Your source CV — header preserved on every tailored output. |
| `temp/outputs/jobs.db` | SQLite store backing the dashboard (persistent across runs). |
| `temp/outputs/runs/<timestamp>/` | Per-run intermediates: search results, JD details, scores, log. |
| `temp/outputs/applications/{job_id}__.../` | Durable per-job artifacts: tailored CV PDF, match result, apply URL. |
| `temp/outputs/applications.csv` | Master log of staged + submitted applications. |
| `temp/outputs/cache/<job_id>.json` | LinkedIn detail cache (7-day TTL). |
| `temp/outputs/launchd.log` | Rolling log when the hourly schedule is active. |

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
tools/db/         → schema.sql, store, ingest
tools/server/     → FastAPI app + pdf_jobs + backfill_jobs
tools/workflow/   → search (the backfill orchestrator)
tools/shared/     → http (curl_cffi + Chrome impersonation), skill_dictionary.yml,
                    ats_questions.yml, prompts/*.md
```
