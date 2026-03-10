"""
Unit tests for AnalysisService.select_unscored (Issue 5.3).

Covers:
- No articles in repo → empty list
- All articles unscored → all returned
- All articles scored → empty list
- Mixed scored/unscored → only unscored returned
- limit=N returns at most N articles
- limit applied AFTER scoring filter (not before)
- limit=0 returns empty list
- source filter forwards to repo and restricts results
- since filter forwards to repo and restricts results
- source + since combined filter works
- source + limit combined works
- calling with no params / default params works
- SelectionParams is a frozen dataclass (immutable)
- scored article is never in the result regardless of position
- articles with scores added after selection are excluded
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

import pytest

from istina.controller.services.analysis_service import AnalysisService, SelectionParams
from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.repositories.memory_repository import MemoryRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _article(n: int, source: str = "test", published_at: Optional[str] = None) -> Article:
    return Article.create(
        title=f"Article {n}",
        url=f"https://example.com/{n}",
        source=source,
        published_at=published_at,
    )


def _score(article: Article) -> BiasScore:
    return BiasScore(
        article_id=article.id,
        provider="mock",
        overall_bias_label="center",
        rhetorical_bias=[],
        claim_checks=[],
        confidence=0.9,
        timestamp=datetime(2026, 2, 22, tzinfo=timezone.utc),
    )


def _repo(*articles: Article) -> MemoryRepository:
    repo = MemoryRepository()
    repo.add_articles(articles)
    return repo


# ---------------------------------------------------------------------------
# Basic selection
# ---------------------------------------------------------------------------

def test_no_articles_returns_empty():
    svc = AnalysisService(repo=MemoryRepository())
    assert svc.select_unscored() == []


def test_all_unscored_returns_all():
    articles = [_article(i) for i in range(4)]
    svc = AnalysisService(repo=_repo(*articles))
    result = svc.select_unscored()
    assert len(result) == 4
    assert all(isinstance(a, Article) for a in result)


def test_all_scored_returns_empty():
    articles = [_article(i) for i in range(3)]
    repo = _repo(*articles)
    for a in articles:
        repo.upsert_bias_score(_score(a))
    svc = AnalysisService(repo=repo)
    assert svc.select_unscored() == []


def test_mixed_returns_only_unscored():
    a1, a2, a3, a4 = [_article(i) for i in range(4)]
    repo = _repo(a1, a2, a3, a4)
    repo.upsert_bias_score(_score(a2))
    repo.upsert_bias_score(_score(a4))
    svc = AnalysisService(repo=repo)
    result = svc.select_unscored()
    ids = {a.id for a in result}
    assert ids == {a1.id, a3.id}


def test_scored_article_never_appears_in_result():
    a = _article(1)
    repo = _repo(a)
    repo.upsert_bias_score(_score(a))
    svc = AnalysisService(repo=repo)
    result = svc.select_unscored()
    assert a.id not in {x.id for x in result}


# ---------------------------------------------------------------------------
# Limit
# ---------------------------------------------------------------------------

def test_limit_caps_result_count():
    articles = [_article(i) for i in range(10)]
    svc = AnalysisService(repo=_repo(*articles))
    result = svc.select_unscored(SelectionParams(limit=3))
    assert len(result) == 3


def test_limit_zero_returns_empty():
    articles = [_article(i) for i in range(5)]
    svc = AnalysisService(repo=_repo(*articles))
    result = svc.select_unscored(SelectionParams(limit=0))
    assert result == []


def test_limit_larger_than_unscored_returns_all_unscored():
    articles = [_article(i) for i in range(3)]
    svc = AnalysisService(repo=_repo(*articles))
    result = svc.select_unscored(SelectionParams(limit=100))
    assert len(result) == 3


def test_limit_applied_after_scoring_filter():
    """
    With 6 articles where every other one is scored (3 scored, 3 unscored),
    limit=2 must return exactly 2 *unscored* articles, not 2 from the full list.
    """
    articles = [_article(i) for i in range(6)]
    repo = _repo(*articles)
    # score articles at even indices: 0, 2, 4
    for i in [0, 2, 4]:
        repo.upsert_bias_score(_score(articles[i]))
    svc = AnalysisService(repo=repo)
    result = svc.select_unscored(SelectionParams(limit=2))
    assert len(result) == 2
    # all returned articles must not have a score
    for a in result:
        assert repo.get_bias_score(a.id) is None


def test_limit_none_returns_all_unscored():
    articles = [_article(i) for i in range(5)]
    svc = AnalysisService(repo=_repo(*articles))
    result = svc.select_unscored(SelectionParams(limit=None))
    assert len(result) == 5


# ---------------------------------------------------------------------------
# Source filter
# ---------------------------------------------------------------------------

def test_source_filter_returns_only_matching_source():
    bbc = [_article(i, source="bbc") for i in range(3)]
    cnn = [_article(i + 10, source="cnn") for i in range(2)]
    repo = _repo(*bbc, *cnn)
    svc = AnalysisService(repo=repo)
    result = svc.select_unscored(SelectionParams(source="bbc"))
    assert all(a.source == "bbc" for a in result)
    assert len(result) == 3


def test_source_filter_with_no_match_returns_empty():
    articles = [_article(i, source="bbc") for i in range(3)]
    svc = AnalysisService(repo=_repo(*articles))
    result = svc.select_unscored(SelectionParams(source="reuters"))
    assert result == []


def test_source_filter_excludes_scored_articles():
    bbc = [_article(i, source="bbc") for i in range(3)]
    repo = _repo(*bbc)
    repo.upsert_bias_score(_score(bbc[1]))  # score middle one
    svc = AnalysisService(repo=repo)
    result = svc.select_unscored(SelectionParams(source="bbc"))
    assert len(result) == 2
    assert bbc[1].id not in {a.id for a in result}


def test_source_and_limit_combined():
    bbc = [_article(i, source="bbc") for i in range(5)]
    cnn = [_article(i + 10, source="cnn") for i in range(5)]
    svc = AnalysisService(repo=_repo(*bbc, *cnn))
    result = svc.select_unscored(SelectionParams(source="bbc", limit=2))
    assert len(result) == 2
    assert all(a.source == "bbc" for a in result)


# ---------------------------------------------------------------------------
# Since filter
# ---------------------------------------------------------------------------

def test_since_filter_excludes_older_articles():
    old = _article(1, published_at="2025-01-01T00:00:00Z")
    new = _article(2, published_at="2026-02-01T00:00:00Z")
    repo = _repo(old, new)
    svc = AnalysisService(repo=repo)
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = svc.select_unscored(SelectionParams(since=cutoff))
    assert len(result) == 1
    assert result[0].id == new.id


def test_since_filter_returns_empty_when_all_too_old():
    articles = [_article(i, published_at="2024-06-01T00:00:00Z") for i in range(3)]
    svc = AnalysisService(repo=_repo(*articles))
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = svc.select_unscored(SelectionParams(since=cutoff))
    assert result == []


def test_since_filter_excludes_scored_articles():
    a1 = _article(1, published_at="2026-02-01T00:00:00Z")
    a2 = _article(2, published_at="2026-02-10T00:00:00Z")
    repo = _repo(a1, a2)
    repo.upsert_bias_score(_score(a1))
    svc = AnalysisService(repo=repo)
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = svc.select_unscored(SelectionParams(since=cutoff))
    assert len(result) == 1
    assert result[0].id == a2.id


# ---------------------------------------------------------------------------
# Source + since combined
# ---------------------------------------------------------------------------

def test_source_and_since_combined():
    matches = [
        _article(1, source="bbc", published_at="2026-02-01T00:00:00Z"),
        _article(2, source="bbc", published_at="2026-02-15T00:00:00Z"),
    ]
    excluded = [
        _article(3, source="bbc", published_at="2024-01-01T00:00:00Z"),  # too old
        _article(4, source="cnn", published_at="2026-02-01T00:00:00Z"),  # wrong source
    ]
    repo = _repo(*matches, *excluded)
    svc = AnalysisService(repo=repo)
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = svc.select_unscored(SelectionParams(source="bbc", since=cutoff))
    ids = {a.id for a in result}
    assert ids == {matches[0].id, matches[1].id}


# ---------------------------------------------------------------------------
# Default / None params
# ---------------------------------------------------------------------------

def test_calling_with_no_params_returns_all_unscored():
    articles = [_article(i) for i in range(4)]
    svc = AnalysisService(repo=_repo(*articles))
    result = svc.select_unscored()
    assert len(result) == 4


def test_calling_with_none_params_same_as_default():
    articles = [_article(i) for i in range(4)]
    svc = AnalysisService(repo=_repo(*articles))
    assert svc.select_unscored(None) == svc.select_unscored()


def test_calling_with_explicit_default_params_same_as_no_params():
    articles = [_article(i) for i in range(4)]
    svc = AnalysisService(repo=_repo(*articles))
    assert svc.select_unscored(SelectionParams()) == svc.select_unscored()


# ---------------------------------------------------------------------------
# SelectionParams immutability
# ---------------------------------------------------------------------------

def test_selection_params_is_frozen():
    params = SelectionParams(limit=5)
    with pytest.raises((AttributeError, TypeError)):
        params.limit = 10  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Late-scoring edge case
# ---------------------------------------------------------------------------

def test_score_added_after_selection_not_retroactively_excluded():
    """
    select_unscored is a snapshot at call time; adding a score after the call
    is fine — it doesn't change the already-returned list.
    """
    a = _article(1)
    repo = _repo(a)
    svc = AnalysisService(repo=repo)
    result = svc.select_unscored()
    assert len(result) == 1

    # Now score it
    repo.upsert_bias_score(_score(a))

    # Result list is already materialized — still contains the article
    assert result[0].id == a.id
    # But a fresh call excludes it
    assert svc.select_unscored() == []
