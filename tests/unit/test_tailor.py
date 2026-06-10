import yaml
from tools.cv.tailor import tailor

PROFILE_YAML = """---
name: Gabor Fekete
title: Senior Engineer
email: x@y.z
phone: "+41"
location: Zurich
summary: Original generic summary.
skills:
  languages: [Java, Python]
  frameworks: [Spring, Kafka]
experience:
  - company: A
    role: R1
    start: "2022"
    end: "now"
    location: Zurich
    highlights: [h0_a, h0_b, h0_c]
    keywords: [Spring]
  - company: B
    role: R2
    start: "2020"
    end: "2022"
    location: Budapest
    highlights: [h1_a, h1_b]
    keywords: [Java]
---
long form
"""

MATCH = {
  "suggested_emphasis": {
    "tailored_summary": "JD-aware summary.",
    "priority_skills": ["Kafka", "Spring"],
    "priority_experiences": [0],
    "priority_bullets": {"0": [0, 2]},
  }
}

def test_tailor_applies_summary_and_priority_skills():
    out_yaml = tailor(PROFILE_YAML, MATCH)
    data = yaml.safe_load(out_yaml)
    assert data["summary"] == "JD-aware summary."
    # priority_skills lead the list, originals follow
    assert data["skills"]["frameworks"][:2] == ["Kafka", "Spring"]

def test_tailor_subsets_highlights_for_priority_experience():
    out_yaml = tailor(PROFILE_YAML, MATCH)
    data = yaml.safe_load(out_yaml)
    exp0 = data["experience"][0]
    assert exp0["highlights"] == ["h0_a", "h0_c"]

def test_tailor_keeps_non_priority_experience_intact():
    out_yaml = tailor(PROFILE_YAML, MATCH)
    data = yaml.safe_load(out_yaml)
    exp1 = data["experience"][1]
    assert exp1["highlights"] == ["h1_a", "h1_b"]
