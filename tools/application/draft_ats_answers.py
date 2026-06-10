"""Draft answers to common ATS questions."""
from __future__ import annotations
import argparse, json, os, re, sys
from pathlib import Path
import yaml
from anthropic import Anthropic

PROMPT_PATH = Path(__file__).resolve().parents[1] / "shared/prompts/ats_answers.md"
QUESTIONS_PATH = Path(__file__).resolve().parents[1] / "shared/ats_questions.yml"
DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

def _extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    return json.loads(text)

def draft_answers(profile_md: str, job_details: dict) -> dict:
    questions = yaml.safe_load(QUESTIONS_PATH.read_text())["questions"]
    job_block = "\n".join(f"{k}: {v}" for k, v in job_details.items() if v)
    questions_block = "\n".join(f"- {q['id']}: {q['text']}" for q in questions)
    prompt = PROMPT_PATH.read_text().format(
        profile=profile_md, job_block=job_block, questions_block=questions_block,
    )
    client = Anthropic()
    msg = client.messages.create(
        model=DEFAULT_MODEL, max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    text_parts = [b.text for b in msg.content if getattr(b, "type", "") == "text"]
    return _extract_json("\n".join(text_parts))

def _format_md(answers: dict, questions: list[dict]) -> str:
    lines = ["# Draft answers — review before submitting", ""]
    for q in questions:
        ans = answers.get(q["id"], "<TODO: draft missing>")
        lines.append(f"## {q['text']}")
        lines.append(ans)
        lines.append("")
    return "\n".join(lines)

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", required=True)
    p.add_argument("--job-details", required=True)
    p.add_argument("-o", required=True)
    args = p.parse_args()
    profile_md = Path(args.profile).read_text()
    job = json.loads(Path(args.job_details).read_text())
    answers = draft_answers(profile_md, job)
    questions = yaml.safe_load(QUESTIONS_PATH.read_text())["questions"]
    Path(args.o).write_text(_format_md(answers, questions))
    print(args.o)
    return 0

if __name__ == "__main__":
    sys.exit(main())
