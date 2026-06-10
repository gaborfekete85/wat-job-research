#!/usr/bin/env bash
# WAT Job Research — one-shot installer.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/gaborfekete85/wat-job-research/main/install.sh | bash
#
# Customise install location with an env var:
#   WAT_INSTALL_DIR=$HOME/projects/wat curl -fsSL .../install.sh | bash
#
# Idempotent: re-running upgrades to latest main.
set -euo pipefail

# ── config ──────────────────────────────────────────────────────────────────
REPO_URL="${WAT_REPO_URL:-https://github.com/gaborfekete85/wat-job-research.git}"
INSTALL_DIR="${WAT_INSTALL_DIR:-$HOME/wat-job-research}"
BRANCH="${WAT_BRANCH:-main}"
PY_REQUIRED_MAJOR_MINOR="3.11"

# ── output helpers ──────────────────────────────────────────────────────────
if [[ -t 1 ]] && command -v tput >/dev/null 2>&1; then
  BOLD="$(tput bold)"; DIM="$(tput dim)"; OK="$(tput setaf 2)"; WARN="$(tput setaf 3)"
  ERR="$(tput setaf 1)"; INFO="$(tput setaf 6)"; RESET="$(tput sgr0)"
else
  BOLD=""; DIM=""; OK=""; WARN=""; ERR=""; INFO=""; RESET=""
fi

say()   { printf "  %s\n" "$*"; }
ok()    { printf "  ${OK}✓${RESET} %s\n" "$*"; }
warn()  { printf "  ${WARN}!${RESET} %s\n" "$*"; }
fail()  { printf "  ${ERR}✗${RESET} %s\n" "$*" >&2; exit 1; }
step()  { printf "\n${BOLD}%s${RESET}\n" "$*"; }

# ── banner ──────────────────────────────────────────────────────────────────
printf "\n${BOLD}WAT Job Research${RESET}  ${DIM}— installer${RESET}\n"
printf "${DIM}───────────────────────────────────────────────${RESET}\n"
say "Repo:    ${INFO}${REPO_URL}${RESET}"
say "Branch:  ${INFO}${BRANCH}${RESET}"
say "Target:  ${INFO}${INSTALL_DIR}${RESET}"

# ── prereqs ─────────────────────────────────────────────────────────────────
step "1/6  Prerequisites"
case "$(uname -s)" in
  Darwin) ok "macOS detected" ;;
  Linux)  ok "Linux detected" ;;
  *)
    fail "Unsupported OS: $(uname -s). On Windows, use WSL2 and re-run inside it."
    ;;
esac

command -v git  >/dev/null 2>&1 || fail "git is required. Install it and re-run."
ok "git found ($(git --version | head -1))"

command -v curl >/dev/null 2>&1 || fail "curl is required."
ok "curl found"

# Find a Python ≥ 3.11
PYTHON=""
for candidate in python3.11 python3.12 python3.13 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c "import sys; assert sys.version_info >= (3, 11), sys.version" 2>/dev/null; then
      PYTHON="$candidate"
      break
    fi
  fi
done
if [[ -z "$PYTHON" ]]; then
  warn "Python ${PY_REQUIRED_MAJOR_MINOR}+ not found on PATH."
  warn "  macOS:  brew install python@${PY_REQUIRED_MAJOR_MINOR}"
  warn "  Debian: apt install python${PY_REQUIRED_MAJOR_MINOR} python${PY_REQUIRED_MAJOR_MINOR}-venv"
  fail "Install Python ${PY_REQUIRED_MAJOR_MINOR}+ and re-run."
fi
ok "Python found ($($PYTHON --version))"

# ── fetch repo ──────────────────────────────────────────────────────────────
step "2/6  Fetch repository"
if [[ -d "$INSTALL_DIR/.git" ]]; then
  say "Existing checkout at ${INSTALL_DIR} — fast-forwarding to origin/${BRANCH}"
  git -C "$INSTALL_DIR" fetch --quiet origin "$BRANCH"
  git -C "$INSTALL_DIR" checkout --quiet "$BRANCH"
  git -C "$INSTALL_DIR" pull --ff-only --quiet
  ok "Updated to $(git -C "$INSTALL_DIR" rev-parse --short HEAD)"
elif [[ -e "$INSTALL_DIR" ]]; then
  fail "${INSTALL_DIR} exists but isn't a git checkout. Move it aside and re-run."
else
  git clone --quiet --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
  ok "Cloned to ${INSTALL_DIR}"
fi
cd "$INSTALL_DIR"

# ── venv + deps ─────────────────────────────────────────────────────────────
step "3/6  Python virtualenv + dependencies"
if [[ ! -d ".venv" ]]; then
  "$PYTHON" -m venv .venv
  ok "Created .venv with $($PYTHON --version)"
else
  ok ".venv already exists — reusing"
fi
# shellcheck disable=SC1091
source .venv/bin/activate

say "Upgrading pip…"
pip install --quiet --upgrade pip

say "Installing project dependencies (this can take 1–2 minutes)…"
pip install --quiet -e ".[dev]"
ok "Dependencies installed"

# ── user-specific files (never overwrite) ──────────────────────────────────
step "4/6  User-specific files (kept private; never overwritten)"
mkdir -p temp/resources temp/outputs

if [[ ! -f .env ]]; then
  cp .env.example .env
  ok "Created .env (placeholder ANTHROPIC_API_KEY — fill it in if you want LLM scoring later)"
else
  ok ".env already exists — kept as-is"
fi

if [[ ! -f temp/resources/profile.md ]]; then
  if [[ -f examples/profile.md ]]; then
    cp examples/profile.md temp/resources/profile.md
    ok "Created temp/resources/profile.md from examples/profile.md — EDIT THIS with your CV"
  else
    warn "examples/profile.md missing in repo — create temp/resources/profile.md manually"
  fi
else
  ok "temp/resources/profile.md already exists — kept as-is"
fi

# ── smoke test ──────────────────────────────────────────────────────────────
step "5/6  Smoke test"
if .venv/bin/python -c "
import requests, curl_cffi, bs4, yaml, jinja2, weasyprint, fitz
from anthropic import Anthropic  # imported but not called
print('OK')" >/dev/null; then
  ok "All Python imports load"
else
  fail "Smoke test failed. See output above."
fi

# ── done ────────────────────────────────────────────────────────────────────
step "6/6  Done"
printf "\n${BOLD}Next steps:${RESET}\n"
printf "\n${DIM}# Move into the project directory${RESET}\n"
printf "  cd %s\n" "$INSTALL_DIR"
printf "\n${DIM}# Replace the placeholder CV with your own${RESET}\n"
printf "  \$EDITOR temp/resources/profile.md\n"
printf "\n${DIM}# (Optional) add your Anthropic API key for LLM scoring${RESET}\n"
printf "  \$EDITOR .env\n"
printf "\n${DIM}# Set your search preferences in SQLite (location + keywords)${RESET}\n"
printf "  ${DIM}# easiest: start the dashboard and use the Preferences panel${RESET}\n"
printf "  .venv/bin/python -m tools.server\n"
printf "  ${DIM}# then visit${RESET} ${INFO}http://localhost:8765${RESET}\n"
printf "\n${DIM}# Or run a backfill directly from the CLI${RESET}\n"
printf "  .venv/bin/python -m tools.workflow.search --days 4 --threshold 0.5\n"
printf "\n${DIM}Documentation:${RESET} %s${INFO}README.md${RESET}\n" "$INSTALL_DIR/"
printf "${DIM}Issues / questions:${RESET} ${INFO}https://github.com/gaborfekete85/wat-job-research/issues${RESET}\n\n"
