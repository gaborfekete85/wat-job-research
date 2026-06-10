from unittest.mock import MagicMock, patch
from tools.application.draft_cover_letter import draft_cover_letter

MOCK_TEXT = "Dear Hiring Manager,\n\nI'd like to apply.\n\nBest,\nGabor"

@patch("tools.application.draft_cover_letter.Anthropic")
def test_draft_returns_markdown(mock_cls):
    c = MagicMock(); mock_cls.return_value = c
    c.messages.create.return_value = MagicMock(
        content=[MagicMock(type="text", text=MOCK_TEXT)]
    )
    out = draft_cover_letter("---\n---", {"title": "X", "company": "Y"}, {"final_score": 0.8})
    assert "I'd like to apply" in out
