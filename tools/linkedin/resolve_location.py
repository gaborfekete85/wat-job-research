"""Resolve a location string to LinkedIn geoIds via the public typeahead endpoint."""
from __future__ import annotations
import argparse, json, sys
from urllib.parse import quote
from tools.shared.http import get

TYPEAHEAD_URL = (
    "https://www.linkedin.com/jobs-guest/api/typeaheadHits"
    "?origin=jserp&typeaheadType=GEO&geoTypes=POPULATED_PLACE,ADMIN_DIVISION_2&query={q}"
)

def parse_typeahead(body: str) -> list[dict]:
    raw = json.loads(body)
    return [{"id": h["id"], "displayName": h["displayName"]} for h in raw[:10]]

def resolve(query: str) -> list[dict]:
    r = get(TYPEAHEAD_URL.format(q=quote(query)), accept="application/json")
    r.raise_for_status()
    return parse_typeahead(r.text)

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("query")
    p.add_argument("--pick-first", action="store_true",
                   help="Output the single best hit instead of the full list")
    args = p.parse_args()
    hits = resolve(args.query)
    if args.pick_first:
        if not hits:
            print("no match", file=sys.stderr); return 1
        print(json.dumps(hits[0]))
    else:
        print(json.dumps(hits, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
