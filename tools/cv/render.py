"""Convert our tailored YAML to rendercv schema and run `rendercv render`."""
from __future__ import annotations
import argparse, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
import yaml


def _rendercv_cmd() -> list[str]:
    """Locate the rendercv CLI — prefer the one alongside this Python interpreter."""
    here = Path(sys.executable).parent / "rendercv"
    if here.exists():
        return [str(here)]
    found = shutil.which("rendercv")
    if found:
        return [found]
    # Last resort: invoke via the current interpreter as a module.
    return [sys.executable, "-m", "rendercv"]

_MONTHS = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "sept": "09", "oct": "10", "nov": "11",
    "dec": "12",
    "january": "01", "february": "02", "march": "03", "april": "04",
    "june": "06", "july": "07", "august": "08", "september": "09",
    "october": "10", "november": "11", "december": "12",
}


def _date(v):
    """Normalize a date value to rendercv format (YYYY-MM, YYYY, or 'present')."""
    if v in (None, ""):
        return None
    s = str(v).strip()
    if s.lower() in ("until now", "present", "now", "current"):
        return "present"
    # Already YYYY-MM
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return s
    # Just YYYY
    if re.fullmatch(r"\d{4}", s):
        return s
    # "2022 Dec" or "Dec 2022"
    m = re.fullmatch(r"(\d{4})\s+([A-Za-z]+)", s)
    if m:
        year, mon = m.group(1), m.group(2).lower()
        if mon in _MONTHS:
            return f"{year}-{_MONTHS[mon]}"
    m = re.fullmatch(r"([A-Za-z]+)\s+(\d{4})", s)
    if m:
        mon, year = m.group(1).lower(), m.group(2)
        if mon in _MONTHS:
            return f"{year}-{_MONTHS[mon]}"
    # Fall through — let rendercv reject it so user sees the issue.
    return s


def to_rendercv_schema(profile: dict, theme: str = "engineeringresumes") -> dict:
    """Maps our profile schema to rendercv's `cv:` shape."""
    def _exp_entry(e: dict) -> dict:
        return {
            "company": e.get("company"),
            "position": e.get("role"),
            "start_date": _date(e.get("start")),
            "end_date": _date(e.get("end")),
            "location": e.get("location"),
            "highlights": e.get("highlights") or [],
        }

    def _flatten_skills(skills: dict | None) -> list[dict]:
        out = []
        for category, items in (skills or {}).items():
            if items:
                out.append({"label": category.replace("_", " ").title(),
                            "details": ", ".join(items)})
        return out

    sections: dict = {}
    summary = profile.get("summary")
    if summary:
        sections["summary"] = [summary]

    exp = profile.get("experience") or []
    if exp:
        sections["experience"] = [_exp_entry(e) for e in exp]

    edu = profile.get("education") or []
    if edu:
        sections["education"] = [{
            "institution": e.get("school"),
            "area": e.get("degree"),
            "start_date": _date(e.get("start")),
            "end_date": _date(e.get("end")),
            "location": e.get("location"),
        } for e in edu]

    skills = _flatten_skills(profile.get("skills"))
    if skills:
        sections["skills"] = skills

    certs = profile.get("certifications") or []
    if certs:
        sections["certifications"] = [
            {"label": c.get("name"),
             "details": f"{c.get('issuer','')} ({c.get('year','')})"}
            for c in certs
        ]

    langs = profile.get("languages") or []
    if langs:
        sections["languages"] = [
            {"label": l.get("name"), "details": l.get("level")} for l in langs
        ]

    return {
        "cv": {
            "name": profile.get("name"),
            "email": profile.get("email"),
            "phone": profile.get("phone"),
            "location": profile.get("location"),
            "social_networks": [
                {"network": "LinkedIn",
                 "username": profile.get("linkedin", "").rstrip("/").split("/")[-1]}
                if profile.get("linkedin") else None,
                {"network": "GitHub",
                 "username": profile.get("github", "").rstrip("/").split("/")[-1]}
                if profile.get("github") else None,
            ],
            "sections": sections,
        },
        "design": {"theme": theme},
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("tailored_yml")
    p.add_argument("-o", dest="output", required=True, help="output PDF path")
    p.add_argument("--theme", default="engineeringresumes")
    args = p.parse_args()
    profile = yaml.safe_load(Path(args.tailored_yml).read_text())
    rendercv_doc = to_rendercv_schema(profile, theme=args.theme)
    # Drop None social entries
    sn = rendercv_doc["cv"].get("social_networks") or []
    rendercv_doc["cv"]["social_networks"] = [s for s in sn if s]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        input_yml = tmp / "input.yml"
        input_yml.write_text(yaml.safe_dump(rendercv_doc, sort_keys=False,
                                            allow_unicode=True))
        proc = subprocess.run(
            _rendercv_cmd() + ["render", str(input_yml),
                               "--output-folder-name", str(tmp / "out")],
            capture_output=True, text=True,
            cwd=str(tmp),
        )
        if proc.returncode != 0:
            print(proc.stderr, file=sys.stderr)
            print(proc.stdout, file=sys.stderr)
            return 1
        pdfs = list((tmp / "out").glob("*.pdf"))
        if not pdfs:
            # Fall back: search the whole tmp dir.
            pdfs = list(tmp.rglob("*.pdf"))
        if not pdfs:
            print("rendercv produced no PDF", file=sys.stderr)
            return 1
        Path(args.output).write_bytes(pdfs[0].read_bytes())
        print(args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
