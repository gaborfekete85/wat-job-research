"""LLM-backed match scorer. One Claude API call per job."""
from __future__ import annotations
import argparse, json, os, re, sys
from pathlib import Path
from anthropic import Anthropic

PROMPT_PATH = Path(__file__).resolve().parents[1] / "shared/prompts/match_score.md"
DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

def _build_prompt(profile_md: str, job: dict, kw: dict) -> str:
    template = PROMPT_PATH.read_text()
    return template.format(
        profile=profile_md,
        title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location", ""),
        seniority=job.get("seniority") or "unspecified",
        employment_type=job.get("employment_type") or "unspecified",
        job_function=job.get("job_function") or "unspecified",
        industry=job.get("industry") or "unspecified",
        description=job.get("description", ""),
        keyword_score=kw.get("score", 0.0),
        matched_skills=", ".join(kw.get("matched", [])) or "(none)",
        missing_skills=", ".join(kw.get("missing", [])) or "(none)",
    )

def _extract_json(text: str) -> dict:
    # Be permissive — strip code fences if present.
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    return json.loads(text)

def score_with_llm(profile_md: str, job_details: dict, keyword_result: dict) -> dict:
    client = Anthropic()
    prompt = _build_prompt(profile_md, job_details, keyword_result)
    msg = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    text_parts = [b.text for b in msg.content if getattr(b, "type", "") == "text"]
    return _extract_json("\n".join(text_parts))

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", required=True)
    p.add_argument("--job-details", required=True)
    p.add_argument("--keyword-result", required=True)
    p.add_argument("-o", dest="output", default=None)
    args = p.parse_args()
    profile_md = Path(args.profile).read_text()
    job = json.loads(Path(args.job_details).read_text())
    kw = json.loads(Path(args.keyword_result).read_text())
    result = score_with_llm(profile_md, job, kw)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload); print(args.output)
    else:
        print(payload)
    return 0

if __name__ == "__main__":
    sys.exit(main())
