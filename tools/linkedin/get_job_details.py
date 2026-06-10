"""Fetch and parse a single LinkedIn job detail page."""
from __future__ import annotations
import argparse, json, sys
from bs4 import BeautifulSoup
from tools.shared.http import get

DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

def _txt(node) -> str:
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""

def parse_detail_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    title = _txt(soup.select_one("h1.top-card-layout__title")) \
            or _txt(soup.select_one("h2.top-card-layout__title"))
    company = _txt(soup.select_one("a.topcard__org-name-link")) \
              or _txt(soup.select_one(".topcard__org-name-link"))
    location = _txt(soup.select_one("span.topcard__flavor--bullet"))
    description = _txt(soup.select_one("div.show-more-less-html__markup"))

    criteria: dict[str, str] = {}
    for item in soup.select("li.description__job-criteria-item"):
        k = _txt(item.select_one(".description__job-criteria-subheader"))
        v = _txt(item.select_one(".description__job-criteria-text"))
        if k and v:
            criteria[k] = v

    apply_link = soup.select_one("a.topcard__link") \
                 or soup.select_one('a[data-tracking-control-name="public_jobs_apply-link-offsite"]')
    apply_url = apply_link.get("href") if apply_link else None

    return {
        "title": title or None,
        "company": company or None,
        "location": location or None,
        "description": description,
        "seniority": criteria.get("Seniority level"),
        "employment_type": criteria.get("Employment type"),
        "job_function": criteria.get("Job function"),
        "industry": criteria.get("Industries"),
        "apply_url": apply_url,
    }

def fetch(job_id: str) -> dict:
    r = get(DETAIL_URL.format(job_id=job_id))
    r.raise_for_status()
    detail = parse_detail_html(r.text)
    detail["job_id"] = job_id
    return detail

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("job_id")
    p.add_argument("-o", dest="output", default=None)
    args = p.parse_args()
    d = fetch(args.job_id)
    payload = json.dumps(d, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w") as f: f.write(payload)
        print(args.output)
    else:
        print(payload)
    return 0

if __name__ == "__main__":
    sys.exit(main())
