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
