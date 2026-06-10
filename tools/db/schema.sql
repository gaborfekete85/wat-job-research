-- WAT Job Search — SQLite schema for the dashboard.
-- One table holds every job ever discovered across all searches.
-- Idempotent: safe to run on every server boot.

CREATE TABLE IF NOT EXISTS jobs (
    id                TEXT PRIMARY KEY,        -- LinkedIn job_id
    title             TEXT NOT NULL,
    company           TEXT NOT NULL,
    location          TEXT,
    description       TEXT NOT NULL,           -- full JD body
    link              TEXT NOT NULL,           -- canonical LinkedIn URL
    apply_url         TEXT,                    -- offsite apply URL if present
    keyword_score     REAL,                    -- 0.0–1.0 from score_keyword
    llm_final_score   REAL,                    -- NULL until LLM scored
    match_result_json TEXT,                    -- full structured match (NULL if not scored)
    tailored_pdf_path TEXT,                    -- absolute path to tailored CV PDF (NULL until rendered)
    status            TEXT NOT NULL DEFAULT 'new',
                                                -- 'new' | 'viewed' | 'staged' | 'submitted' | 'dismissed'
    discovered_at     TEXT NOT NULL,           -- ISO UTC; set on first insert only
    viewed_at         TEXT,
    staged_at         TEXT,
    submitted_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status        ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_discovered_at ON jobs(discovered_at DESC);
