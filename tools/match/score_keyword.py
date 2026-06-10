"""Deterministic keyword overlap scoring: score = |jd ∩ profile| / |jd|."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from tools.match.extract_skills import extract_from_profile_yaml, extract_from_text

def score(profile_skills: set[str], jd_skills: set[str]) -> dict:
    if not jd_skills:
        return {"score": 0.0, "matched": [], "missing": [], "jd_skills": []}
    matched = sorted(profile_skills & jd_skills)
    missing = sorted(jd_skills - profile_skills)
    return {
        "score": len(matched) / len(jd_skills),
        "matched": matched,
        "missing": missing,
        "jd_skills": sorted(jd_skills),
    }

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", required=True)
    p.add_argument("--jd", required=True, help="path to JD text file")
    args = p.parse_args()
    profile_skills = extract_from_profile_yaml(Path(args.profile).read_text())
    jd_skills = extract_from_text(Path(args.jd).read_text())
    print(json.dumps(score(profile_skills, jd_skills), indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
