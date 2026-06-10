# Find and Apply to Jobs

Purpose: Search LinkedIn for jobs matching the user's profile, score each
against `temp/resources/profile.md`, and stage tailored applications for
the best matches.

## Prerequisites
- `temp/resources/profile.md` exists.
- `.env` contains `ANTHROPIC_API_KEY`.
- `pip install -e ".[dev]"` has been run.
- `rendercv` is installed (`pip install "rendercv[full]"` if missing).

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

All Python invocations use `python -m tools.X.Y` style (the project uses
`packages = []` in `pyproject.toml`, so direct script paths don't resolve
the internal `tools.shared.http` import).

1. **Resolve location.** Run `python -m tools.linkedin.resolve_location "<location>" --pick-first`.
   Save the returned `id` as `geo_id`. If multiple Switzerland options exist
   in the non-`--pick-first` output, prefer the one whose `displayName` matches
   the user's intent.

2. **Search jobs.** Run
   `python -m tools.linkedin.search_jobs --keywords <kw> --geo-id <geo_id> [--posted-within-hours N] --limit N -o <run_dir>/jobs_raw.json`.

3. **For each job in `jobs_raw.json`:**
   3a. Check `temp/outputs/cache/<job_id>.json`. If present and `cached_at`
       is within 7 days and (for keyword/llm scores) newer than `profile.md` mtime,
       reuse cached fields. Else call `python -m tools.linkedin.get_job_details <job_id>`
       and write to cache.
   3b. Run `python -m tools.match.extract_skills --source jd` on the JD text, then
       `python -m tools.match.score_keyword --profile temp/resources/profile.md --jd <jd_file>`.
   3c. If keyword score < `--filter-cutoff` → skip this job; log "filtered".
   3d. Run `python -m tools.match.score_llm` with the JD details and keyword result.
   3e. If `final_score < --accept-threshold` → log "below threshold"; continue.
   3f. Else:
       - `python -m tools.cv.tailor` → `tailored_cv.yml`
       - `python -m tools.cv.render` → `tailored_cv.pdf`
       - If `--with-cover-letter`: `python -m tools.application.draft_cover_letter`
       - If `--with-ats-answers`: `python -m tools.application.draft_ats_answers`
       - `python -m tools.application.stage` to assemble the folder.

4. **Print summary table** to stdout (counts of search/filtered/matched/accepted).

5. **Next-action checklist** — for each staged application, print:
   - `open temp/outputs/applications/{job_id}__*/apply_url.txt`
   - `python -m tools.application.mark_submitted {job_id}`

## Outputs

- `temp/outputs/runs/<timestamp>/` — intermediates (`jobs_raw.json`,
  `jobs_with_details.json`, `jobs_filtered.json`, `jobs_matched.json`, `run.log`).
- `temp/outputs/applications/{job_id}__{company}__{slug}/` — durable per-job folder.
- `temp/outputs/applications.csv` — master log.
- `temp/outputs/cache/<job_id>.json` — cache (7d TTL).

## Mode A (single command) shortcut

For batch runs, `./tools/run.sh` chains all the above steps with the same
flags. The agent mode (this file) and the bash mode (`run.sh`) mirror each
other step-for-step.
