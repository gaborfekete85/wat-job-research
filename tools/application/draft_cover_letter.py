"""Draft a cover letter using profile + JD + match analysis. One LLM call."""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from anthropic import Anthropic

PROMPT_PATH = Path(__file__).resolve().parents[1] / "shared/prompts/cover_letter.md"
DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

def draft_cover_letter(profile_md: str, job_details: dict, match_result: dict) -> str:
    job_block = "\n".join(f"{k}: {v}" for k, v in job_details.items() if v)
    match_block = json.dumps(match_result.get("suggested_emphasis", {}), indent=2)
    prompt = PROMPT_PATH.read_text().format(
        profile=profile_md, job_block=job_block, match_block=match_block,
    )
    client = Anthropic()
    msg = client.messages.create(
        model=DEFAULT_MODEL, max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    text_parts = [b.text for b in msg.content if getattr(b, "type", "") == "text"]
    return "\n".join(text_parts).strip()

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", required=True)
    p.add_argument("--job-details", required=True)
    p.add_argument("--match-result", required=True)
    p.add_argument("-o", required=True)
    args = p.parse_args()
    md = draft_cover_letter(
        Path(args.profile).read_text(),
        json.loads(Path(args.job_details).read_text()),
        json.loads(Path(args.match_result).read_text()),
    )
    Path(args.o).write_text(md)
    print(args.o)
    return 0

if __name__ == "__main__":
    sys.exit(main())
