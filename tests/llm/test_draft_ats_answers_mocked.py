import json
from unittest.mock import MagicMock, patch
from tools.application.draft_ats_answers import draft_answers

MOCK_JSON = {"motivation": "I'm interested because…", "salary_expectations": "<TODO: confirm>"}

@patch("tools.application.draft_ats_answers.Anthropic")
def test_draft_returns_q_a(mock_cls):
    c = MagicMock(); mock_cls.return_value = c
    c.messages.create.return_value = MagicMock(
        content=[MagicMock(type="text", text=json.dumps(MOCK_JSON))]
    )
    out = draft_answers("---\n---", {"title": "X"})
    assert out["motivation"].startswith("I'm interested")
    assert "<TODO" in out["salary_expectations"]
