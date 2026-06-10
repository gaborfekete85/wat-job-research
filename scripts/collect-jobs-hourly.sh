#!/usr/bin/env bash
# scripts/collect-jobs-hourly.sh
# Fired hourly by ~/Library/LaunchAgents/com.feketegabor.wat-collect-jobs.plist
# (see the "Scheduling" section in README.md).
#
# Runs one backfill against LinkedIn — paginated search → keyword score → dedup
# insert into temp/outputs/jobs.db — and appends a timestamped log block to
# temp/outputs/launchd.log.
#
# Manual run for testing:
#   ./scripts/collect-jobs-hourly.sh           # default flags
#   ./scripts/collect-jobs-hourly.sh --days 7  # forwards any args to the CLI
set -euo pipefail

# Project root = parent of this script's directory.
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Load .env (mostly for the ANTHROPIC_API_KEY — the backfill itself doesn't
# need it, but it's harmless and lets future scoring steps reuse the script).
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

LOG_DIR="temp/outputs"
LOG="$LOG_DIR/launchd.log"
mkdir -p "$LOG_DIR"

{
  echo "─────────────────────────────────────────────"
  echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)  /collect-jobs"
  echo "─────────────────────────────────────────────"
  .venv/bin/python -m tools.workflow.search "$@"
  echo
} >> "$LOG" 2>&1
