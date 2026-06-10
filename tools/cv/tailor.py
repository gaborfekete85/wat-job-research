"""Build a tailored rendercv-shaped YAML from profile.md + match_result."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import yaml

def _parse_profile(profile_md: str) -> dict:
    parts = profile_md.split("---", 2)
    return yaml.safe_load(parts[1]) if len(parts) >= 3 else {}

def tailor(profile_md: str, match_result: dict) -> str:
    profile = _parse_profile(profile_md)
    emp = (match_result or {}).get("suggested_emphasis", {})

    # Replace summary if tailored one is provided
    if emp.get("tailored_summary"):
        profile["summary"] = emp["tailored_summary"]

    # Reorder skills — lead with priority_skills, dedupe
    priority = list(emp.get("priority_skills") or [])
    if profile.get("skills") and priority:
        for category, items in (profile["skills"] or {}).items():
            if not items:
                continue
            originals = [s for s in items if s not in priority]
            leading = [s for s in priority if s in items]
            profile["skills"][category] = leading + originals

    # Subset highlights for priority experiences
    bullets = emp.get("priority_bullets") or {}
    for idx_str, keep in bullets.items():
        try:
            i = int(idx_str)
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(profile.get("experience") or []):
            highlights = profile["experience"][i].get("highlights") or []
            profile["experience"][i]["highlights"] = [highlights[k] for k in keep
                                                     if 0 <= k < len(highlights)]

    return yaml.safe_dump(profile, sort_keys=False, allow_unicode=True)

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", required=True)
    p.add_argument("--match-result", required=True)
    p.add_argument("-o", required=True)
    args = p.parse_args()
    out = tailor(Path(args.profile).read_text(),
                 json.loads(Path(args.match_result).read_text()))
    Path(args.o).write_text(out)
    print(args.o)
    return 0

if __name__ == "__main__":
    sys.exit(main())
