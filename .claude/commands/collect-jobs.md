---
description: Run the LinkedIn job-collection backfill (paginated search → keyword score → dedup insert)
argument-hint: [--days N] [--threshold 0.5] [--max-results N]
allowed-tools: Bash
---

You are the WAT job-search backfill operator.

**What the user just asked for:** run the backfill workflow with these optional
flags: $ARGUMENTS

## Steps

1. **Capture the pre-run DB state** so you can report what changed:

   ```bash
   sqlite3 temp/outputs/jobs.db "SELECT status, COUNT(*) FROM jobs GROUP BY status"
   ```

2. **Run the workflow.** Use the project venv. Pass `$ARGUMENTS` through
   verbatim — the CLI already pulls keywords + location + location_geo_id
   from the saved DB preferences, so a bare invocation is fine:

   ```bash
   .venv/bin/python -m tools.workflow.search $ARGUMENTS
   ```

   This typically takes 1–4 minutes:
   - Pagination over the LinkedIn public guest endpoints
   - 1.5s polite throttle per HTTP request
   - Cache-aware JD detail fetch (re-runs are fast)
   - Pure deterministic keyword scoring (no LLM, no API spend)

3. **Capture the post-run DB state.**

4. **Summarize for the user** in 5–10 lines:
   - Headline: how long it took and how many new rows landed in NEW vs
     FILTERED_OUT.
   - Bucket diff (status → before / after / change).
   - **Top 5 newest-and-above-0.65** matches in NEW (sorted by keyword
     score DESC, ranked-recent-discovered first) — show
     `company · title (score)`. Skip if zero added.
   - If `inserted_filtered_out` is non-zero, mention the user can review
     them in the dashboard's "Filtered Out" tab.

   Use the existing helper queries:
   ```bash
   sqlite3 -header -column temp/outputs/jobs.db "
     SELECT substr(company, 1, 22) AS company,
            substr(title, 1, 50) AS title,
            printf('%.2f', keyword_score) AS kw
     FROM jobs
     WHERE status='new' AND keyword_score >= 0.65
       AND date(discovered_at) = date('now')
     ORDER BY discovered_at DESC, keyword_score DESC
     LIMIT 5"
   ```

5. **Remind the user the dashboard is at** `http://localhost:8765` if you
   notice the server isn't running (check with
   `lsof -ti :8765 || echo 'server not running'`). Don't start it
   yourself — just mention the command.

## Constraints

- This task uses ZERO Anthropic API credits (no LLM scoring). Don't
  conflate it with the optional Phase 3 of the full pipeline.
- If `profile/profile.md` is missing or `.venv/bin/python` doesn't
  exist, stop and tell the user.
- If LinkedIn returns 429 (rate-limited), the run aborts cleanly — surface
  the error and suggest waiting an hour before retrying.
