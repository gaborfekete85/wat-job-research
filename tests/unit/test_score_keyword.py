from tools.match.score_keyword import score


def test_full_match_scores_1():
    r = score({"Java", "AWS"}, {"Java", "AWS"})
    assert r["score"] == 1.0


def test_no_match_scores_0():
    r = score({"Java"}, {"Rust"})
    assert r["score"] == 0.0


def test_partial_match():
    # JD needs Java, AWS, Kafka. Profile has Java + AWS only.
    r = score({"Java", "AWS"}, {"Java", "AWS", "Kafka"})
    assert abs(r["score"] - 2 / 3) < 1e-6
    assert set(r["matched"]) == {"Java", "AWS"}
    assert r["missing"] == ["Kafka"]


def test_empty_jd_skills_returns_zero():
    r = score({"Java"}, set())
    assert r["score"] == 0.0
