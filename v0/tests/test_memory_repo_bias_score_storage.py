from datetime import datetime, timedelta

from istina.model.repositories.memory_repository import MemoryRepository
from istina.model.entities.bias_score import BiasScore


def _make_score(article_id: str, confidence: float, ts: datetime) -> BiasScore:
    """
    Helper that matches the BiasScore you showed earlier.
    Adjust ONLY if your BiasScore constructor differs.
    """
    return BiasScore(
        article_id=article_id,
        provider="mock",
        overall_bias_label="center",
        rhetorical_bias=["loaded_language"],
        claim_checks=[{"claim": "x", "verdict": "unknown"}],
        confidence=confidence,
        timestamp=ts,
        raw_response={"raw": "ok"},
    )


def test_get_bias_score_missing_returns_none():
    repo = MemoryRepository()
    assert repo.get_bias_score("does-not-exist") is None


def test_upsert_then_get_returns_score():
    repo = MemoryRepository()

    ts = datetime.utcnow()
    score = _make_score(article_id="a1", confidence=0.8, ts=ts)

    repo.upsert_bias_score(score)

    got = repo.get_bias_score("a1")
    assert got is not None
    assert got.article_id == "a1"
    assert got.provider == "mock"
    assert got.overall_bias_label == "center"
    assert got.confidence == 0.8
    assert got.timestamp == ts


def test_upsert_overwrites_existing_latest_wins():
    repo = MemoryRepository()

    t0 = datetime.utcnow()
    t1 = t0 + timedelta(seconds=10)

    older = _make_score(article_id="a1", confidence=0.2, ts=t0)
    newer = _make_score(article_id="a1", confidence=0.9, ts=t1)

    repo.upsert_bias_score(older)
    got1 = repo.get_bias_score("a1")
    assert got1 is not None
    assert got1.confidence == 0.2
    assert got1.timestamp == t0

    # Upsert again with same article_id -> should replace
    repo.upsert_bias_score(newer)
    got2 = repo.get_bias_score("a1")
    assert got2 is not None
    assert got2.confidence == 0.9
    assert got2.timestamp == t1

    # Internal storage should still have exactly one score for that article_id
    assert len(repo._bias_scores) == 1
    assert repo._bias_scores["a1"].confidence == 0.9
