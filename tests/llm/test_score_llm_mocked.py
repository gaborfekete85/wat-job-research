import json
from unittest.mock import MagicMock, patch
from tools.match.score_llm import score_with_llm

MOCK_RESPONSE_JSON = {
    "final_score": 0.82,
    "skills_match": 0.85,
    "seniority_fit": "fit",
    "location_fit": True,
    "matched_skills": ["AWS", "Kafka"],
    "missing_critical": [],
    "reasoning": "Strong cloud + event-driven match.",
    "suggested_emphasis": {
        "tailored_summary": "Senior engineer with 15+ years in distributed systems...",
        "priority_skills": ["AWS", "Kafka", "Kubernetes"],
        "priority_experiences": [0, 1],
        "priority_bullets": {"0": [0, 2, 5]},
    },
}

@patch("tools.match.score_llm.Anthropic")
def test_score_with_llm_returns_parsed_json(mock_cls):
    client = MagicMock()
    mock_cls.return_value = client
    client.messages.create.return_value = MagicMock(
        content=[MagicMock(type="text", text=json.dumps(MOCK_RESPONSE_JSON))]
    )
    result = score_with_llm(
        profile_md="--- \n---",
        job_details={"title": "X", "company": "Y", "location": "Z",
                     "seniority": "Senior", "employment_type": "FT",
                     "job_function": "Eng", "industry": "Fintech",
                     "description": "..."},
        keyword_result={"score": 0.6, "matched": ["AWS"], "missing": ["Rust"]},
    )
    assert result["final_score"] == 0.82
    assert result["suggested_emphasis"]["priority_skills"][0] == "AWS"
