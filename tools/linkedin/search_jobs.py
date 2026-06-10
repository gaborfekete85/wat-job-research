"""Search LinkedIn jobs via public guest endpoint and parse the HTML cards."""
from __future__ import annotations
import argparse, json, sys, time
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from tools.shared.http import get

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
PAGE_SIZE = 25

def _txt(node) -> str:
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""

def parse_search_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for card in soup.select("div.base-card"):
        urn = card.get("data-entity-urn", "")
        job_id = urn.split(":")[-1] if "jobPosting" in urn else ""
        title = _txt(card.select_one("h3.base-search-card__title"))
        company = _txt(card.select_one("h4.base-search-card__subtitle"))
        location = _txt(card.select_one(".job-search-card__location"))
        time_tag = card.select_one("time")
        posted = time_tag.get("datetime") if time_tag else None
        link = card.select_one("a.base-card__full-link")
        url = link["href"].split("?")[0] if link else ""
        if job_id and title and company:
            out.append({
                "job_id": job_id, "title": title, "company": company,
                "location": location, "posted": posted, "url": url,
            })
    return out

def search(keywords: str, geo_id: str, *, posted_within_hours: int | None,
           limit: int) -> list[dict]:
    results: list[dict] = []
    start = 0
    while len(results) < limit:
        params = {"keywords": keywords, "geoId": geo_id, "start": start}
        if posted_within_hours:
            params["f_TPR"] = f"r{posted_within_hours * 3600}"
        url = f"{SEARCH_URL}?{urlencode(params)}"
        r = get(url)
        if r.status_code == 429:
            raise RuntimeError("LinkedIn returned 429 — rate limited")
        r.raise_for_status()
        page = parse_search_html(r.text)
        if not page:
            break
        results.extend(page)
        if len(page) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return results[:limit]

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--keywords", required=True)
    p.add_argument("--geo-id", required=True)
    p.add_argument("--posted-within-hours", type=int, default=None)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("-o", dest="output", default=None)
    args = p.parse_args()
    jobs = search(args.keywords, args.geo_id,
                  posted_within_hours=args.posted_within_hours, limit=args.limit)
    payload = json.dumps(jobs, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, "w") as f: f.write(payload)
        print(args.output)
    else:
        print(payload)
    return 0

if __name__ == "__main__":
    sys.exit(main())
