# Find and Apply to Jobs

> **Execution mode:** Claude Desktop only. Open this directory in Claude Desktop,
> ask Claude to "find me jobs matching X, generate tailored CVs," and it will follow
> the steps below.

Purpose: Search LinkedIn for jobs matching the user's profile, score each against
`temp/resources/profile.md`, and stage tailored applications (with the source CV's
preserved header) for the best matches.

## Prerequisites
- `temp/resources/profile.md` exists (the user's structured profile YAML).
- `temp/resources/gabor-fekete_<TIMESTAMP>.pdf` exists (the source CV whose header —
  QR codes, photo, contact, LinkedIn/GitHub links — will be preserved on all
  tailored output). Use the latest one in that folder if multiple exist.
- `.env` contains `ANTHROPIC_API_KEY` (only needed for the LLM scoring step;
  the deterministic phases run without it).
- Python deps installed: `pip install -e ".[dev]"` (with a working `.venv`).

## Inputs

Claude should first read saved preferences from the dashboard DB:
`sqlite3 temp/outputs/jobs.db "SELECT key, value FROM preferences"` — or just
hit `GET http://localhost:8765/api/preferences` if the server is running. Use
those values as defaults; ask the user only if a preference is missing/empty.

| Flag | Source | Default | Notes |
|---|---|---|---|
| `location` | DB preference `location` | "Zurich, Switzerland" | Resolved via LinkedIn typeahead → geoId at run time |
| `location_geo_id` | DB preference `location_geo_id` (optional) | none | When set (via dashboard confirm-on-pick), use directly and skip resolve_location |
| `keywords` | DB preference `keywords` | "ai OR software developer OR consultant" | LinkedIn supports OR boolean |
| `posted_within_hours` | CLI arg / ask | 72 | LinkedIn `f_TPR` filter |
| `limit` | CLI arg / ask | 15 | Max jobs to fetch |
| `filter_cutoff` | CLI arg / ask | 0.4 | Below this keyword score, LLM is not called |
| `accept_threshold` | CLI arg / ask | 0.7 | At/above this final score, a tailored CV is generated |
| `with_cover_letter` | CLI arg / ask | false | Opt-in LLM call to draft cover letter markdown |
| `with_ats_answers` | CLI arg / ask | false | Opt-in LLM call to draft common ATS question answers |

## Steps Claude follows

All Python invocations use `python -m tools.X.Y` form (the project's `pyproject.toml`
declares `packages = []`, so direct script-path invocation breaks the internal
`tools.shared.http` import).

1. **Set up the run directory.** Create `temp/outputs/runs/<UTC-timestamp>/`.
   Use that as `RUN_DIR` for intermediates.

2. **Resolve the location** → geoId.
   - **If the DB preference `location_geo_id` is set, use it directly — skip
     the typeahead call.** This is the dashboard's confirm-on-pick result; the
     user has already disambiguated.
   - Otherwise, run `python -m tools.linkedin.resolve_location "<location>" --pick-first`
     and save the `id` field as `geo_id`. If multiple Switzerland entries exist
     in the non-`--pick-first` form, prefer the displayName the user means
     (Zurich vs Zürich Metropolitan Area).

3. **Search jobs.**
   `python -m tools.linkedin.search_jobs --keywords "<kw>" --geo-id <geo_id> --posted-within-hours <N> --limit <L> -o <RUN_DIR>/jobs_raw.json`

4. **For each job in `jobs_raw.json`:**

   - **Cache lookup:** check `temp/outputs/cache/<job_id>.json`. If present and the
     stored `cached_at` is within 7 days (and, for keyword/llm scores, newer than
     `profile.md`'s mtime), reuse it. Else call `python -m tools.linkedin.get_job_details <job_id>`
     and write the result into the cache file as `{"job_detail": ..., "cached_at": ...}`.

   - **Keyword pre-filter (deterministic, free):** run
     `tools.match.extract_skills` on the JD description text + on `profile.md`,
     then `tools.match.score_keyword`. Attach the result as `job["keyword_score"]`.
     Drop jobs where `score < filter_cutoff`.

   - **LLM scoring (paid, requires ANTHROPIC_API_KEY):**
     `python -m tools.match.score_llm --profile temp/resources/profile.md --job-details <jd.json> --keyword-result <kw.json>`
     returns the full structured result including `final_score`, `seniority_fit`,
     `location_fit`, `matched_skills`, `missing_critical`, `reasoning`, and
     `suggested_emphasis`. Attach as `job["llm_score"]` and cache it.

   Write the per-job results to `<RUN_DIR>/jobs_matched.json` (one array, all scored
   jobs including those above and below `accept_threshold`).

4b. **Ingest scored jobs into the dashboard DB.**
   `python -m tools.db.ingest --jobs <RUN_DIR>/jobs_matched.json`
   Upserts every scored job into `temp/outputs/jobs.db`. New jobs land with
   `status='new'`. Jobs already in the DB keep their existing status (so
   previously-viewed jobs stay in the VIEWED column) but get their content +
   scores refreshed.

5. **For each accepted job (`final_score ≥ accept_threshold`):**

   - **Tailor the CV YAML:**
     `python -m tools.cv.tailor --profile temp/resources/profile.md --match-result <match.json> -o <APP_DIR>/tailored.yml`

   - **Render the tailored CV PDF — WITH the source header preserved:**
     `python -m tools.cv.render_with_source_header --source temp/resources/<source>.pdf --tailored-yml <APP_DIR>/tailored.yml -o <APP_DIR>/tailored_cv.pdf`
     (This uses WeasyPrint for the body + pymupdf for the header overlay.)

   - **Optional artifacts:**
     - If `with_cover_letter`: `python -m tools.application.draft_cover_letter`
     - If `with_ats_answers`: `python -m tools.application.draft_ats_answers`

   - **Stage the application:**
     `python -m tools.application.stage --job-details <jd.json> --cv <APP_DIR>/tailored_cv.pdf --match-result <match.json> [--cover-letter ...] [--ats-answers ...]`
     This creates `temp/outputs/applications/<job_id>__<company>__<slug>/` with all
     the artifacts and appends a row to `temp/outputs/applications.csv`.

6. **Summarize for the user:**
   - search count, filter-pass count, LLM-scored count, accepted count, staged count
   - For each staged job: print the apply URL and the mark-submitted command:
     `python -m tools.application.mark_submitted <job_id> --notes "..."`
   - Remind the user the dashboard is available — see step 7.

7. **(Optional) Open the dashboard.** `python -m tools.server` then visit
   `http://localhost:8765`. The dashboard reads `temp/outputs/jobs.db` and lets the
   user trigger the same `tailor` + `render_with_source_header` + `stage_application`
   pipeline from a "Generate PDF" button (button is disabled for jobs without an
   LLM score; if so, ask Claude to run LLM scoring first).

## When the API key isn't available

Claude should still run steps 1-4 (everything up to the keyword pre-filter is
deterministic and free) and present the candidate list to the user. Then run step 4b
with `jobs_filtered.json` (the keyword-only result, no LLM scores) so the dashboard
shows the jobs with "needs LLM" badges. The user can then ask Claude to hand-craft
a `match.json` with `suggested_emphasis` for specific high-interest jobs, then
proceed to step 5 to render the tailored CVs.

## Outputs

- `temp/outputs/runs/<timestamp>/` — intermediates (`jobs_raw.json`, `jobs_with_details.json`,
  `jobs_filtered.json`, `jobs_matched.json`).
- `temp/outputs/applications/{job_id}__{company}__{slug}/` — durable per-job folder
  (job_details.json, match_result.json, tailored.yml, tailored_cv.pdf, optional
  cover_letter.md / ats_answers.md, apply_url.txt, submitted.json after marking).
- `temp/outputs/applications.csv` — master log.
- `temp/outputs/cache/<job_id>.json` — cache (7-day TTL).
- `temp/outputs/jobs.db` — SQLite store backing the dashboard (one row per discovered
  job, persistent across runs).
