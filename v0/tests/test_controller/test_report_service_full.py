"""
Unit tests for ReportService.get_full_report.

Uses MemoryRepository directly — no mocking of internal collaborators.

Covers:
- Return type is list of (Article, BiasScore | None) tuples
- Empty repo → empty list
- Unscored article → BiasScore slot is None
- Scored article → BiasScore slot is the correct BiasScore instance
- Mixed batch: scored and unscored coexist in the same result
- article_id filter → exactly one pair returned for a known article
- article_id filter → empty list for an unknown article_id
- article_id filter → BiasScore is None when the article is not yet scored
- article_id filter → BiasScore is present when the article is scored
- article_id filter ignores limit and source kwargs
- source filter → only matching-source pairs returned
- source filter → non-matching articles absent from result
- limit filter → at most N pairs returned
- limit=0 → empty list
- limit larger than repo → all pairs returned
- ordering is deterministic (published_at DESC, consistent across calls)
- each pair's Article matches its BiasScore.article_id when score is present
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

import pytest

from istina.controller.services.report_service import ReportService
from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.repositories.memory_repository import MemoryRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2026, 2, 22, tzinfo=timezone.utc)


def _article(n: int, source: str = "test", published_at: Optional[str] = None) -> Article:
    return Article.create(
        title=f"Article {n}",
        url=f"https://example.com/{n}",
        source=source,
        published_at=published_at,
    )


def _score(article: Article, label: str = "center") -> BiasScore:
    return BiasScore(
        article_id=article.id,
        provider="mock",
        overall_bias_label=label,
        rhetorical_bias=[],
        claim_checks=[],
        confidence=0.9,
        timestamp=_TS,
    )


def _repo(*articles: Article) -> MemoryRepository:
    repo = MemoryRepository()
    if articles:
        repo.add_articles(articles)
    return repo


def _svc(repo: MemoryRepository) -> ReportService:
    return ReportService(repo=repo)


FullRow = Tuple[Article, Optional[BiasScore]]


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

def test_get_full_report_returns_list():
    result = _svc(MemoryRepository()).get_full_report()
    assert isinstance(result, list)


def test_get_full_report_rows_are_tuples_of_length_two():
    a = _article(1)
    repo = _repo(a)
    result = _svc(repo).get_full_report()
    assert len(result) == 1
    assert isinstance(result[0], tuple)
    assert len(result[0]) == 2


def test_get_full_report_first_element_is_article():
    a = _article(1)
    result = _svc(_repo(a)).get_full_report()
    assert isinstance(result[0][0], Article)


# ---------------------------------------------------------------------------
# Empty repo
# ---------------------------------------------------------------------------

def test_empty_repo_returns_empty_list():
    assert _svc(MemoryRepository()).get_full_report() == []


# ---------------------------------------------------------------------------
# Score slot — None vs BiasScore
# ---------------------------------------------------------------------------

def test_unscored_article_score_slot_is_none():
    a = _article(1)
    result = _svc(_repo(a)).get_full_report()
    assert result[0][1] is None


def test_scored_article_score_slot_is_bias_score():
    a = _article(1)
    repo = _repo(a)
    repo.upsert_bias_score(_score(a))
    result = _svc(repo).get_full_report()
    assert isinstance(result[0][1], BiasScore)


def test_scored_article_score_has_correct_article_id():
    a = _article(1)
    repo = _repo(a)
    repo.upsert_bias_score(_score(a))
    _, score = _svc(repo).get_full_report()[0]
    assert score.article_id == a.id


def test_mixed_batch_scored_and_unscored():
    a_scored, a_unscored = _article(1), _article(2)
    repo = _repo(a_scored, a_unscored)
    repo.upsert_bias_score(_score(a_scored))
    result = _svc(repo).get_full_report()
    score_map = {row[0].id: row[1] for row in result}
    assert score_map[a_scored.id] is not None
    assert score_map[a_unscored.id] is None


def test_all_unscored_all_score_slots_none():
    articles = [_article(i) for i in range(4)]
    result = _svc(_repo(*articles)).get_full_report()
    assert all(score is None for _, score in result)


def test_all_scored_no_none_slots():
    articles = [_article(i) for i in range(4)]
    repo = _repo(*articles)
    for a in articles:
        repo.upsert_bias_score(_score(a))
    result = _svc(repo).get_full_report()
    assert all(score is not None for _, score in result)


# ---------------------------------------------------------------------------
# article_id filter
# ---------------------------------------------------------------------------

def test_article_id_filter_returns_exactly_one_pair():
    a1, a2, a3 = _article(1), _article(2), _article(3)
    repo = _repo(a1, a2, a3)
    result = _svc(repo).get_full_report(article_id=a2.id)
    assert len(result) == 1


def test_article_id_filter_returns_correct_article():
    a1, a2 = _article(1), _article(2)
    repo = _repo(a1, a2)
    result = _svc(repo).get_full_report(article_id=a1.id)
    assert result[0][0].id == a1.id


def test_article_id_filter_unknown_id_returns_empty_list():
    repo = _repo(_article(1))
    assert _svc(repo).get_full_report(article_id="does-not-exist") == []


def test_article_id_filter_score_none_when_unscored():
    a = _article(1)
    result = _svc(_repo(a)).get_full_report(article_id=a.id)
    assert result[0][1] is None


def test_article_id_filter_score_present_when_scored():
    a = _article(1)
    repo = _repo(a)
    repo.upsert_bias_score(_score(a))
    _, score = _svc(repo).get_full_report(article_id=a.id)[0]
    assert isinstance(score, BiasScore)
    assert score.article_id == a.id


def test_article_id_filter_ignores_limit():
    # limit=0 should be irrelevant when article_id is given
    a = _article(1)
    result = _svc(_repo(a)).get_full_report(article_id=a.id, limit=0)
    assert len(result) == 1


def test_article_id_filter_ignores_source():
    # source filter should not apply when article_id is given
    a = _article(1, source="bbc")
    result = _svc(_repo(a)).get_full_report(article_id=a.id, source="cnn")
    assert len(result) == 1
    assert result[0][0].id == a.id


# ---------------------------------------------------------------------------
# source filter
# ---------------------------------------------------------------------------

def test_source_filter_returns_only_matching_source():
    bbc = [_article(i, source="bbc") for i in range(3)]
    cnn = [_article(i + 10, source="cnn") for i in range(2)]
    repo = _repo(*bbc, *cnn)
    result = _svc(repo).get_full_report(source="bbc")
    assert len(result) == 3
    assert all(a.source == "bbc" for a, _ in result)


def test_source_filter_excludes_other_sources():
    bbc = [_article(i, source="bbc") for i in range(2)]
    cnn = [_article(i + 10, source="cnn") for i in range(2)]
    repo = _repo(*bbc, *cnn)
    result = _svc(repo).get_full_report(source="bbc")
    returned_sources = {a.source for a, _ in result}
    assert "cnn" not in returned_sources


def test_source_filter_no_match_returns_empty_list():
    repo = _repo(_article(1, source="bbc"))
    assert _svc(repo).get_full_report(source="reuters") == []


# ---------------------------------------------------------------------------
# limit filter
# ---------------------------------------------------------------------------

def test_limit_caps_result_length():
    articles = [_article(i) for i in range(10)]
    result = _svc(_repo(*articles)).get_full_report(limit=4)
    assert len(result) == 4


def test_limit_zero_returns_empty_list():
    articles = [_article(i) for i in range(5)]
    result = _svc(_repo(*articles)).get_full_report(limit=0)
    assert result == []


def test_limit_larger_than_repo_returns_all():
    articles = [_article(i) for i in range(3)]
    result = _svc(_repo(*articles)).get_full_report(limit=100)
    assert len(result) == 3


def test_limit_one_returns_single_pair():
    articles = [_article(i) for i in range(5)]
    result = _svc(_repo(*articles)).get_full_report(limit=1)
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Ordering is deterministic
# ---------------------------------------------------------------------------

def test_ordering_is_deterministic_across_calls():
    articles = [_article(i) for i in range(6)]
    repo = _repo(*articles)
    svc = _svc(repo)
    ids_first  = [a.id for a, _ in svc.get_full_report()]
    ids_second = [a.id for a, _ in svc.get_full_report()]
    assert ids_first == ids_second


def test_ordering_published_at_desc():
    # articles with explicit timestamps — newest should come first
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    older = _article(1, published_at=(base).isoformat())
    newer = _article(2, published_at=(base + timedelta(days=1)).isoformat())
    repo = _repo(older, newer)
    result = _svc(repo).get_full_report()
    assert result[0][0].id == newer.id
    assert result[1][0].id == older.id


# ---------------------------------------------------------------------------
# Integrity: each pair's Article.id matches BiasScore.article_id
# ---------------------------------------------------------------------------

def test_article_id_matches_score_article_id_for_all_scored_rows():
    articles = [_article(i) for i in range(5)]
    repo = _repo(*articles)
    for a in articles:
        repo.upsert_bias_score(_score(a))
    result = _svc(repo).get_full_report()
    for article, score in result:
        assert score is not None
        assert score.article_id == article.id
