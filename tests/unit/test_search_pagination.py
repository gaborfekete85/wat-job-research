"""Tests for the paginated search() loop in tools.linkedin.search_jobs.

Covers the bug fixed in commit ____: LinkedIn returns 10 per page (variable),
NOT 25 — the previous loop stopped after the first short page and silently
limited every search to 10 jobs.
"""
from __future__ import annotations
from unittest.mock import MagicMock, patch

from tools.linkedin import search_jobs


def _fake_resp(html: str, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.text = html
    r.raise_for_status = MagicMock()
    return r


def _card(job_id: str) -> str:
    return f"""
      <li><div class="base-card" data-entity-urn="urn:li:jobPosting:{job_id}">
        <a class="base-card__full-link" href="https://x/{job_id}"></a>
        <h3 class="base-search-card__title">Senior Engineer</h3>
        <h4 class="base-search-card__subtitle"><a class="hidden-nested-link">ACME</a></h4>
        <span class="job-search-card__location">Zurich</span>
        <time datetime="2026-06-10"></time>
      </div></li>"""


def _page(*job_ids: str) -> str:
    return "".join(_card(j) for j in job_ids)


def test_search_walks_multiple_pages_even_when_pages_have_only_10():
    """Regression: the previous PAGE_SIZE=25 + len(page)<PAGE_SIZE: break
    logic stopped after one page. LinkedIn returns 10 per page; we must keep
    going until an empty (or duplicate-only) page comes back.
    """
    pages = [
        _page("1", "2", "3", "4", "5", "6", "7", "8", "9", "10"),
        _page("11", "12", "13", "14", "15", "16", "17", "18", "19", "20"),
        _page("21", "22", "23"),
        _page(),  # empty → stop
    ]
    responses = [_fake_resp(p) for p in pages]

    with patch("tools.linkedin.search_jobs.get", side_effect=responses):
        jobs = search_jobs.search("engineer", "107814425",
                                  posted_within_hours=None, limit=100)
    ids = [j["job_id"] for j in jobs]
    assert ids == [str(i) for i in range(1, 24)]


def test_search_advances_by_actual_page_size_not_25():
    captured_starts: list[int] = []

    def capture(url, **kw):
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(url).query)
        captured_starts.append(int(qs["start"][0]))
        # Return 2 short pages, then empty
        idx = len(captured_starts) - 1
        pages = [
            _page("a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8", "a9", "a10"),
            _page("b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8", "b9", "b10"),
            _page(),
        ]
        return _fake_resp(pages[idx])

    with patch("tools.linkedin.search_jobs.get", side_effect=capture):
        jobs = search_jobs.search("engineer", "X",
                                  posted_within_hours=None, limit=100)

    # After page 0 (10 items), start should be 10 — NOT 25
    assert captured_starts == [0, 10, 20]
    assert len(jobs) == 20


def test_search_stops_when_only_duplicates_return():
    """LinkedIn sometimes echoes earlier cards once you've walked past the
    real result set. Bail out cleanly instead of looping forever."""
    page0 = _page("1", "2", "3")
    page1 = _page("1", "2", "3")  # exact repeat
    responses = [_fake_resp(page0), _fake_resp(page1)]

    with patch("tools.linkedin.search_jobs.get", side_effect=responses):
        jobs = search_jobs.search("engineer", "X",
                                  posted_within_hours=None, limit=100)
    assert [j["job_id"] for j in jobs] == ["1", "2", "3"]


def test_search_respects_limit():
    page0 = _page("1", "2", "3", "4", "5", "6", "7", "8", "9", "10")
    page1 = _page("11", "12", "13", "14", "15")
    responses = [_fake_resp(page0), _fake_resp(page1)]
    with patch("tools.linkedin.search_jobs.get", side_effect=responses):
        jobs = search_jobs.search("engineer", "X",
                                  posted_within_hours=None, limit=12)
    assert len(jobs) == 12


def test_search_429_raises():
    with patch("tools.linkedin.search_jobs.get",
               side_effect=[_fake_resp("", status=429)]):
        try:
            search_jobs.search("engineer", "X",
                                posted_within_hours=None, limit=10)
        except RuntimeError as e:
            assert "429" in str(e)
        else:
            raise AssertionError("expected RuntimeError on 429")
