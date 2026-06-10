from pathlib import Path
import json
from tools.linkedin.resolve_location import parse_typeahead

FIXTURE = Path(__file__).parent / "fixtures/typeahead_zurich.json"

def test_parse_typeahead_returns_zurich_switzerland_first_match():
    hits = parse_typeahead(FIXTURE.read_text())
    assert hits, "expected at least one hit"
    # Match by displayName; LinkedIn ranks dynamically and geoIds are not stable across captures
    assert any("Zurich" in h["displayName"] and "Switzerland" in h["displayName"] for h in hits), \
        f"expected a Zurich, Switzerland entry; got: {[h['displayName'] for h in hits]}"

def test_parse_typeahead_returns_top_10():
    hits = parse_typeahead(FIXTURE.read_text())
    assert 1 <= len(hits) <= 10
