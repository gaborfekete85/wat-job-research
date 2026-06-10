"""Extract canonical skills from JD text or profile.md, using skill_dictionary.yml."""
from __future__ import annotations
import argparse, functools, json, re, sys
from pathlib import Path
import yaml

DICT_PATH = Path(__file__).resolve().parents[1] / "shared/skill_dictionary.yml"

@functools.lru_cache(maxsize=1)
def _compile_patterns() -> list[tuple[str, re.Pattern]]:
    """Returns list of (canonical_name, compiled_regex). Patterns match any variant
    on word boundaries, case-insensitive."""
    data = yaml.safe_load(DICT_PATH.read_text())
    out: list[tuple[str, re.Pattern]] = []
    for _category, terms in data.items():
        for canonical, variants in terms.items():
            all_terms = [canonical, *variants]
            # Escape; use \b for ASCII variants. Variants like "c++" need
            # raw boundary handling since \b doesn't separate +.
            parts = []
            for t in all_terms:
                esc = re.escape(t.strip())
                # Use lookarounds for non-word boundaries instead of \b
                parts.append(rf"(?<![A-Za-z0-9+#]){esc}(?![A-Za-z0-9+#])")
            pat = re.compile("|".join(parts), re.IGNORECASE)
            out.append((canonical, pat))
    return out

def extract_from_text(text: str) -> set[str]:
    return {canonical for canonical, pat in _compile_patterns() if pat.search(text)}

def extract_from_profile_yaml(profile_yaml: str) -> set[str]:
    """Read structured YAML frontmatter + long-form body. Frontmatter skills
    are taken as-is; body text scanned with dictionary."""
    found: set[str] = set()
    parts = profile_yaml.split("---", 2)
    if len(parts) >= 3:
        front = yaml.safe_load(parts[1]) or {}
        body = parts[2]
        for _cat, items in (front.get("skills") or {}).items():
            for s in items or []:
                # Normalize via dictionary if possible (e.g., "k8s" -> "Kubernetes")
                matches = extract_from_text(str(s))
                if matches:
                    found |= matches
                else:
                    found.add(str(s))
        # Also include 'keywords' on each experience
        for exp in front.get("experience") or []:
            for k in exp.get("keywords") or []:
                matches = extract_from_text(str(k))
                if matches:
                    found |= matches
                else:
                    found.add(str(k))
        found |= extract_from_text(body)
    else:
        found |= extract_from_text(profile_yaml)
    return found

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["profile", "jd"], required=True)
    p.add_argument("--input", help="path to file; if omitted, reads stdin")
    args = p.parse_args()
    text = Path(args.input).read_text() if args.input else sys.stdin.read()
    skills = (extract_from_profile_yaml if args.source == "profile" else extract_from_text)(text)
    print(json.dumps({"skills": sorted(skills)}, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
