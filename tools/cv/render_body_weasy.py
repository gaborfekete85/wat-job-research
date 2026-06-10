"""Render a tailored CV body PDF (Summary + Experience + ...) via HTML+CSS+WeasyPrint.

Replaces rendercv as the body-renderer because rendercv 2.3 (the last version
compatible with Python 3.11) has a Typst bug that rejects non-default margins.

The output PDF is meant to be composed UNDER a source PDF header by
`tools/cv/render_with_source_header.py`. Top margin is sized to leave space
for the source header to be stamped on top of page 1.
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML, CSS

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
TEMPLATE_NAME = "cv_body.html.j2"

# Top-margin for body PDF in centimetres. Source header is 180pt ≈ 6.35cm tall;
# we leave 6.5cm so body content starts just below the header on page 1.
DEFAULT_TOP_MARGIN_CM = 6.5


def render_body(tailored_yml_path: Path, output: Path, *,
                top_margin_cm: float = DEFAULT_TOP_MARGIN_CM) -> Path:
    profile = yaml.safe_load(tailored_yml_path.read_text())

    context = {
        "summary": profile.get("summary", "").strip(),
        "experience": profile.get("experience") or [],
        "education": profile.get("education") or [],
        "certifications": profile.get("certifications") or [],
        "projects": profile.get("projects") or [],
        "languages": profile.get("languages") or [],
        "hobbies": _flatten_hobbies(profile.get("hobbies")),
        "top_margin_cm": top_margin_cm,
    }

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    html_str = env.get_template(TEMPLATE_NAME).render(**context)

    output.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html_str).write_pdf(str(output))
    return output


def _flatten_hobbies(v) -> str:
    if not v:
        return ""
    if isinstance(v, list):
        return " · ".join(str(x) for x in v)
    return str(v)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("tailored_yml", help="path to tailored YAML (from tailor.py)")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--top-margin-cm", type=float, default=DEFAULT_TOP_MARGIN_CM)
    args = p.parse_args()
    out = render_body(Path(args.tailored_yml), Path(args.output),
                      top_margin_cm=args.top_margin_cm)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
