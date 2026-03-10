"""
Unit tests for ReportService.get_summary (Issue 5.5).

Uses MemoryRepository directly — no mocking of internal collaborators.

Covers:
- Return type is SummaryReport
- SummaryReport has all required fields
- Empty repo → total_articles=0, analyzed_count=0, empty dicts
- total_articles counts every article regardless of scoring
- analyzed_count counts only articles with a BiasScore in repo
- analyzed_count=0 when no scores exist
- analyzed_count equals number of scored articles in a mixed repo
- counts_by_source: correct grouping and tallies
- counts_by_source: include_by_source=False → empty dict
- counts_by_overall_label: correct grouping across labels
- counts_by_overall_label: include_by_overall_label=False → empty dict
- counts_by_overall_label: only scored articles contribute
- source filter forwarded to repo (unmatched sources excluded)
- limit filter forwarded to repo
- counts_by_source excluded when include_by_source=False but total still correct
- counts_by_overall_label excluded when flag=False but analyzed_count still correct
- multiple articles from same source accumulate correctly
- multiple articles with same label accumulate correctly
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

import pytest

from istina.controller.services.report_service import ReportService, SummaryReport
from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.repositories.memory_repository import MemoryRepository


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_TS = datetime(2026, 2, 22, tzinfo=timezone.utc)


def _article(n: int, source: str = "test") -> Article:
    return Article.create(
        title=f"Article {n}",
        url=f"https://example.com/{n}",
        source=source,
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


# ---------------------------------------------------------------------------
# Return type and fields
# ---------------------------------------------------------------------------

def test_get_summary_returns_summary_report():
    svc = _svc(MemoryRepository())
    result = svc.get_summary()
    assert isinstance(result, SummaryReport)


def test_summary_report_has_all_fields():
    r = _svc(MemoryRepository()).get_summary()
    assert hasattr(r, "total_articles")
    assert hasattr(r, "analyzed_count")
    assert hasattr(r, "counts_by_source")
    assert hasattr(r, "counts_by_overall_label")


# ---------------------------------------------------------------------------
# Empty repo
# ---------------------------------------------------------------------------

def test_empty_repo_total_articles_is_zero():
    assert _svc(MemoryRepository()).get_summary().total_articles == 0


def test_empty_repo_analyzed_count_is_zero():
    assert _svc(MemoryRepository()).get_summary().analyzed_count == 0


def test_empty_repo_counts_by_source_is_empty():
    assert _svc(MemoryRepository()).get_summary().counts_by_source == {}


def test_empty_repo_counts_by_overall_label_is_empty():
    assert _svc(MemoryRepository()).get_summary().counts_by_overall_label == {}


# ---------------------------------------------------------------------------
# total_articles
# ---------------------------------------------------------------------------

def test_total_articles_counts_all_regardless_of_scoring():
    articles = [_article(i) for i in range(5)]
    repo = _repo(*articles)
    # Score only 2 of them
    repo.upsert_bias_score(_score(articles[0]))
    repo.upsert_bias_score(_score(articles[1]))
    r = _svc(repo).get_summary()
    assert r.total_articles == 5


def test_total_articles_single():
    assert _svc(_repo(_article(1))).get_summary().total_articles == 1


def test_total_articles_zero_unscored():
    # All articles unscored — total still correct
    repo = _repo(*[_article(i) for i in range(3)])
    assert _svc(repo).get_summary().total_articles == 3


# ---------------------------------------------------------------------------
# analyzed_count
# ---------------------------------------------------------------------------

def test_analyzed_count_zero_when_no_scores():
    repo = _repo(*[_article(i) for i in range(4)])
    assert _svc(repo).get_summary().analyzed_count == 0


def test_analyzed_count_equals_scored_articles():
    articles = [_article(i) for i in range(5)]
    repo = _repo(*articles)
    for a in articles[:3]:
        repo.upsert_bias_score(_score(a))
    assert _svc(repo).get_summary().analyzed_count == 3


def test_analyzed_count_all_scored():
    articles = [_article(i) for i in range(4)]
    repo = _repo(*articles)
    for a in articles:
        repo.upsert_bias_score(_score(a))
    assert _svc(repo).get_summary().analyzed_count == 4


def test_analyzed_count_single_scored():
    a = _article(1)
    repo = _repo(a)
    repo.upsert_bias_score(_score(a))
    assert _svc(repo).get_summary().analyzed_count == 1


# ---------------------------------------------------------------------------
# counts_by_source
# ---------------------------------------------------------------------------

def test_counts_by_source_groups_correctly():
    bbc = [_article(i, source="bbc") for i in range(3)]
    cnn = [_article(i + 10, source="cnn") for i in range(2)]
    repo = _repo(*bbc, *cnn)
    r = _svc(repo).get_summary()
    assert r.counts_by_source == {"bbc": 3, "cnn": 2}


def test_counts_by_source_single_source():
    articles = [_article(i, source="reuters") for i in range(4)]
    r = _svc(_repo(*articles)).get_summary()
    assert r.counts_by_source == {"reuters": 4}


def test_counts_by_source_accumulates_same_source():
    # 5 articles from one source: should be a single key with value 5
    articles = [_article(i, source="bbc") for i in range(5)]
    r = _svc(_repo(*articles)).get_summary()
    assert r.counts_by_source["bbc"] == 5


def test_counts_by_source_false_returns_empty_dict():
    articles = [_article(i, source="bbc") for i in range(3)]
    r = _svc(_repo(*articles)).get_summary(include_by_source=False)
    assert r.counts_by_source == {}


def test_counts_by_source_false_does_not_affect_total():
    articles = [_article(i) for i in range(3)]
    r = _svc(_repo(*articles)).get_summary(include_by_source=False)
    assert r.total_articles == 3


def test_counts_by_source_counts_all_articles_not_just_scored():
    # counts_by_source should include EVERY article (scored or not)
    a1, a2, a3 = _article(1, "bbc"), _article(2, "bbc"), _article(3, "bbc")
    repo = _repo(a1, a2, a3)
    repo.upsert_bias_score(_score(a1))  # only 1 scored
    r = _svc(repo).get_summary()
    assert r.counts_by_source == {"bbc": 3}


# ---------------------------------------------------------------------------
# counts_by_overall_label
# ---------------------------------------------------------------------------

def test_counts_by_overall_label_groups_correctly():
    articles = [_article(i) for i in range(5)]
    repo = _repo(*articles)
    repo.upsert_bias_score(_score(articles[0], "left"))
    repo.upsert_bias_score(_score(articles[1], "left"))
    repo.upsert_bias_score(_score(articles[2], "right"))
    repo.upsert_bias_score(_score(articles[3], "center"))
    # articles[4] unscored — should not appear in label counts
    r = _svc(repo).get_summary()
    assert r.counts_by_overall_label == {"left": 2, "right": 1, "center": 1}


def test_counts_by_overall_label_only_scored_articles_contribute():
    a_scored = _article(1)
    a_unscored = _article(2)
    repo = _repo(a_scored, a_unscored)
    repo.upsert_bias_score(_score(a_scored, "center"))
    r = _svc(repo).get_summary()
    assert r.counts_by_overall_label == {"center": 1}


def test_counts_by_overall_label_accumulates_same_label():
    articles = [_article(i) for i in range(4)]
    repo = _repo(*articles)
    for a in articles:
        repo.upsert_bias_score(_score(a, "center"))
    r = _svc(repo).get_summary()
    assert r.counts_by_overall_label == {"center": 4}


def test_counts_by_overall_label_false_returns_empty_dict():
    a = _article(1)
    repo = _repo(a)
    repo.upsert_bias_score(_score(a, "left"))
    r = _svc(repo).get_summary(include_by_overall_label=False)
    assert r.counts_by_overall_label == {}


def test_counts_by_overall_label_false_does_not_affect_analyzed_count():
    articles = [_article(i) for i in range(3)]
    repo = _repo(*articles)
    for a in articles:
        repo.upsert_bias_score(_score(a, "center"))
    r = _svc(repo).get_summary(include_by_overall_label=False)
    assert r.analyzed_count == 3


def test_counts_by_overall_label_empty_when_no_scores():
    articles = [_article(i) for i in range(3)]
    r = _svc(_repo(*articles)).get_summary()
    assert r.counts_by_overall_label == {}


# ---------------------------------------------------------------------------
# Both flags False
# ---------------------------------------------------------------------------

def test_both_flags_false_still_returns_correct_totals():
    articles = [_article(i) for i in range(5)]
    repo = _repo(*articles)
    for a in articles[:2]:
        repo.upsert_bias_score(_score(a))
    r = _svc(repo).get_summary(include_by_source=False, include_by_overall_label=False)
    assert r.total_articles == 5
    assert r.analyzed_count == 2
    assert r.counts_by_source == {}
    assert r.counts_by_overall_label == {}


# ---------------------------------------------------------------------------
# Filters forwarded to repo
# ---------------------------------------------------------------------------

def test_source_filter_excludes_other_sources():
    bbc = [_article(i, source="bbc") for i in range(3)]
    cnn = [_article(i + 10, source="cnn") for i in range(4)]
    repo = _repo(*bbc, *cnn)
    r = _svc(repo).get_summary(source="bbc")
    assert r.total_articles == 3
    assert "cnn" not in r.counts_by_source


def test_source_filter_analyzed_count_only_matching():
    bbc = [_article(i, source="bbc") for i in range(3)]
    cnn = [_article(i + 10, source="cnn") for i in range(2)]
    repo = _repo(*bbc, *cnn)
    for a in bbc:
        repo.upsert_bias_score(_score(a, "center"))
    for a in cnn:
        repo.upsert_bias_score(_score(a, "left"))
    r = _svc(repo).get_summary(source="bbc")
    assert r.analyzed_count == 3
    assert r.counts_by_overall_label == {"center": 3}


def test_limit_filter_caps_total_articles():
    articles = [_article(i) for i in range(10)]
    r = _svc(_repo(*articles)).get_summary(limit=4)
    assert r.total_articles == 4
