"""Validate skill_dictionary.yml shape."""
from pathlib import Path
import yaml

DICT_PATH = Path(__file__).resolve().parents[2] / "tools/shared/skill_dictionary.yml"

def test_dictionary_loads():
    data = yaml.safe_load(DICT_PATH.read_text())
    assert isinstance(data, dict) and data, "must be a non-empty mapping of categories"

def test_categories_are_terms_to_variants():
    data = yaml.safe_load(DICT_PATH.read_text())
    for category, terms in data.items():
        assert isinstance(terms, dict), f"{category} must be a mapping of canonical → variants"
        for canonical, variants in terms.items():
            assert isinstance(canonical, str) and canonical
            assert isinstance(variants, list) and all(isinstance(v, str) for v in variants)
            assert variants, f"{canonical} has empty variants list"
            assert all(v.strip() for v in variants), f"{canonical} has blank/whitespace variant"
            assert len(variants) == len({v.lower() for v in variants}), \
                f"{canonical} has duplicate variants (case-insensitive)"

def test_has_minimum_seed_entries():
    data = yaml.safe_load(DICT_PATH.read_text())
    total = sum(len(terms) for terms in data.values())
    assert total >= 80, f"expected ≥80 canonical entries, got {total}"

def test_no_variant_collisions_across_canonicals():
    """A variant string must not map to two different canonicals — that would create
    ambiguous regex matches in extract_skills.py."""
    data = yaml.safe_load(DICT_PATH.read_text())
    seen: dict[str, str] = {}  # variant_lower -> canonical
    for _category, terms in data.items():
        for canonical, variants in terms.items():
            for v in variants:
                key = v.lower()
                if key in seen and seen[key] != canonical:
                    raise AssertionError(
                        f"variant '{v}' appears under both '{seen[key]}' and '{canonical}'"
                    )
                seen[key] = canonical

def test_does_not_explode():
    """Guardrail against accidental dump-and-explode. ~200 is well above current 90."""
    data = yaml.safe_load(DICT_PATH.read_text())
    total = sum(len(terms) for terms in data.values())
    assert total <= 200, f"dictionary suspiciously large: {total}"
