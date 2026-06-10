"""Render a tailored CV preserving the source PDF's header (QR codes, photo, links).

Composition strategy:
  1. Render tailored body via WeasyPrint (HTML+CSS) — gives clean margins and full
     width control (avoids rendercv 2.3's margin bug).
  2. Stamp the source PDF's top region (the header — name, contact, photo, QR codes)
     onto a new A4 page using pymupdf's show_pdf_page (vector preserving — QR codes
     stay scannable, links stay clickable).
  3. Compose: source header on top + body PDF below (no scaling, no stretch).
  4. Copy subsequent body pages as-is.

The body PDF is rendered with a top margin (6.5cm by default) that leaves room
for the source header to be stamped on top of page 1 without any content collision.
"""
from __future__ import annotations
import argparse, sys, tempfile
from pathlib import Path
import fitz  # pymupdf

from tools.cv.render_body_weasy import render_body, DEFAULT_TOP_MARGIN_CM

A4 = (595.276, 841.890)  # points
SOURCE_HEADER_END_Y = 180        # source PDF: header ends here (separator below QRs)


def compose(source_pdf: Path, tailored_yml: Path, output: Path,
            *, header_height: float = SOURCE_HEADER_END_Y,
            body_top_margin_cm: float = DEFAULT_TOP_MARGIN_CM) -> Path:
    """Compose final tailored CV: source header + WeasyPrint-rendered body."""
    src = fitz.open(str(source_pdf))

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmpf:
        body_pdf_path = Path(tmpf.name)
    try:
        render_body(tailored_yml, body_pdf_path, top_margin_cm=body_top_margin_cm)
        body = fitz.open(str(body_pdf_path))

        out = fitz.open()
        page_w, page_h = A4

        for i in range(len(body)):
            new_page = out.new_page(width=page_w, height=page_h)

            # Stamp the full body page (no scaling — body already has the right
            # top margin to leave space for the header).
            new_page.show_pdf_page(
                fitz.Rect(0, 0, page_w, page_h),
                body, i,
            )

            if i == 0:
                # Stamp source PDF header on top of page 1
                src_page = src[0]
                new_page.show_pdf_page(
                    fitz.Rect(0, 0, page_w, header_height),
                    src, 0,
                    clip=fitz.Rect(0, 0, src_page.rect.width, header_height),
                )

        output.parent.mkdir(parents=True, exist_ok=True)
        out.save(str(output))
        out.close(); body.close(); src.close()
        return output
    finally:
        body_pdf_path.unlink(missing_ok=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, help="path to source PDF with header to preserve")
    p.add_argument("--tailored-yml", required=True, help="path to tailored YAML (from tailor.py)")
    p.add_argument("-o", "--output", required=True, help="output PDF path")
    p.add_argument("--header-height", type=float, default=SOURCE_HEADER_END_Y,
                   help=f"y-coordinate where source header ends (default {SOURCE_HEADER_END_Y})")
    p.add_argument("--body-top-margin-cm", type=float, default=DEFAULT_TOP_MARGIN_CM,
                   help=f"top margin (cm) of the body PDF (default {DEFAULT_TOP_MARGIN_CM})")
    args = p.parse_args()
    out = compose(
        Path(args.source), Path(args.tailored_yml), Path(args.output),
        header_height=args.header_height,
        body_top_margin_cm=args.body_top_margin_cm,
    )
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
