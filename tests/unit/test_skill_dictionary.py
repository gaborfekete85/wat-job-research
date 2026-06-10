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

def test_has_minimum_seed_entries():
    data = yaml.safe_load(DICT_PATH.read_text())
    total = sum(len(terms) for terms in data.values())
    assert total >= 80, f"expected ≥80 canonical entries, got {total}"
