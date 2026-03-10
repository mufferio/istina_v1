"""
Unit tests for AnalysisService.analyze (Issue 5.4).

Uses a MockProvider that produces real BiasScore objects so the full
pipeline (select → analyze → persist) is exercised end-to-end with
MemoryRepository — no mocking of internal collaborators.

Covers:
- analyze() returns AnalyzeResult
- analyzed_count equals the number of unscored articles
- scores are persisted to the repo (get_bias_score returns them after)
- skipped_count / failed_count start at 0 on a clean run
- errors list is empty on a clean run
- calling analyze() twice: second run skips already-scored articles
- provider exception → failed_count incremented, error recorded, run continues
- provider returns mismatched article_id → skipped_count incremented, not persisted
- mixed batch: some succeed, some fail → counts add up correctly
- SelectionParams.limit forwarded: only N articles analyzed
- SelectionParams.source forwarded: only matching articles analyzed
- analyze() with no params uses all unscored articles
- empty repo → analyzed_count == 0, no errors
- MockProvider receives the correct Article object
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

import pytest

from istina.controller.services.analysis_service import (
    AnalysisService,
    AnalyzeResult,
    SelectionParams,
)
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


def _make_score(article: Article) -> BiasScore:
    return BiasScore(
        article_id=article.id,
        provider="mock",
        overall_bias_label="center",
        rhetorical_bias=[],
        claim_checks=[],
        confidence=0.9,
        timestamp=_TS,
    )


def _repo(*articles: Article) -> MemoryRepository:
    repo = MemoryRepository()
    repo.add_articles(articles)
    return repo


# ---------------------------------------------------------------------------
# MockProvider
# ---------------------------------------------------------------------------

class MockProvider:
    """
    Deterministic BiasProvider that always returns a valid BiasScore.

    Optional hooks:
      raise_for_ids  – set of article IDs that should raise RuntimeError
      wrong_id_for   – set of article IDs where the returned score has a
                       deliberately wrong article_id (to test skip logic)
      calls          – list of Article objects actually passed to analyze_article
    """

    def __init__(
        self,
        raise_for_ids: Optional[set] = None,
        wrong_id_for: Optional[set] = None,
    ):
        self.raise_for_ids: set = raise_for_ids or set()
        self.wrong_id_for: set = wrong_id_for or set()
        self.calls: List[Article] = []

    def analyze_article(self, article: Article) -> BiasScore:
        self.calls.append(article)
        if article.id in self.raise_for_ids:
            raise RuntimeError(f"simulated provider failure for {article.id}")
        if article.id in self.wrong_id_for:
            return BiasScore(
                article_id="wrong-id-000",
                provider="mock",
                overall_bias_label="unknown",
                rhetorical_bias=[],
                claim_checks=[],
                confidence=0.5,
                timestamp=_TS,
            )
        return _make_score(article)


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

def test_analyze_returns_analyze_result():
    svc = AnalysisService(repo=MemoryRepository())
    result = svc.analyze(MockProvider())
    assert isinstance(result, AnalyzeResult)


def test_analyze_result_has_all_fields():
    svc = AnalysisService(repo=MemoryRepository())
    r = svc.analyze(MockProvider())
    assert hasattr(r, "analyzed_count")
    assert hasattr(r, "skipped_count")
    assert hasattr(r, "failed_count")
    assert hasattr(r, "errors")


# ---------------------------------------------------------------------------
# analyzed_count == number of unscored articles
# ---------------------------------------------------------------------------

def test_analyzed_count_equals_unscored_count():
    articles = [_article(i) for i in range(5)]
    svc = AnalysisService(repo=_repo(*articles))
    r = svc.analyze(MockProvider())
    assert r.analyzed_count == 5


def test_analyzed_count_single_article():
    svc = AnalysisService(repo=_repo(_article(1)))
    r = svc.analyze(MockProvider())
    assert r.analyzed_count == 1


def test_empty_repo_analyzed_count_is_zero():
    svc = AnalysisService(repo=MemoryRepository())
    r = svc.analyze(MockProvider())
    assert r.analyzed_count == 0
    assert r.skipped_count == 0
    assert r.failed_count == 0
    assert r.errors == []


# ---------------------------------------------------------------------------
# Scores are persisted to the repo
# ---------------------------------------------------------------------------

def test_scores_are_persisted_after_analyze():
    articles = [_article(i) for i in range(3)]
    repo = _repo(*articles)
    svc = AnalysisService(repo=repo)
    svc.analyze(MockProvider())
    for a in articles:
        assert repo.get_bias_score(a.id) is not None, f"score missing for {a.id}"


def test_persisted_score_has_correct_article_id():
    a = _article(1)
    repo = _repo(a)
    svc = AnalysisService(repo=repo)
    svc.analyze(MockProvider())
    stored = repo.get_bias_score(a.id)
    assert stored.article_id == a.id


def test_persisted_score_is_a_bias_score_instance():
    a = _article(1)
    repo = _repo(a)
    svc = AnalysisService(repo=repo)
    svc.analyze(MockProvider())
    assert isinstance(repo.get_bias_score(a.id), BiasScore)


def test_all_scores_persisted_for_batch():
    articles = [_article(i) for i in range(6)]
    repo = _repo(*articles)
    svc = AnalysisService(repo=repo)
    svc.analyze(MockProvider())
    assert all(repo.get_bias_score(a.id) is not None for a in articles)


# ---------------------------------------------------------------------------
# Clean run — zero skipped / failed
# ---------------------------------------------------------------------------

def test_clean_run_skipped_count_is_zero():
    articles = [_article(i) for i in range(4)]
    svc = AnalysisService(repo=_repo(*articles))
    r = svc.analyze(MockProvider())
    assert r.skipped_count == 0


def test_clean_run_failed_count_is_zero():
    articles = [_article(i) for i in range(4)]
    svc = AnalysisService(repo=_repo(*articles))
    r = svc.analyze(MockProvider())
    assert r.failed_count == 0


def test_clean_run_errors_is_empty():
    articles = [_article(i) for i in range(4)]
    svc = AnalysisService(repo=_repo(*articles))
    r = svc.analyze(MockProvider())
    assert r.errors == []


# ---------------------------------------------------------------------------
# Second run skips already-scored articles
# ---------------------------------------------------------------------------

def test_second_analyze_call_scores_nothing_already_scored():
    articles = [_article(i) for i in range(3)]
    repo = _repo(*articles)
    svc = AnalysisService(repo=repo)
    svc.analyze(MockProvider())       # first run: scores all 3
    r2 = svc.analyze(MockProvider())  # second run: all already scored
    assert r2.analyzed_count == 0
    assert r2.skipped_count == 0
    assert r2.failed_count == 0


# ---------------------------------------------------------------------------
# Provider failure → failed_count, error recorded, run continues
# ---------------------------------------------------------------------------

def test_provider_exception_increments_failed_count():
    a1, a2, a3 = _article(1), _article(2), _article(3)
    repo = _repo(a1, a2, a3)
    provider = MockProvider(raise_for_ids={a2.id})
    svc = AnalysisService(repo=repo)
    r = svc.analyze(provider)
    assert r.failed_count == 1


def test_provider_exception_records_error_message():
    a = _article(1)
    repo = _repo(a)
    provider = MockProvider(raise_for_ids={a.id})
    svc = AnalysisService(repo=repo)
    r = svc.analyze(provider)
    assert len(r.errors) == 1
    assert a.id in r.errors[0]


def test_provider_exception_does_not_stop_remaining_articles():
    articles = [_article(i) for i in range(4)]
    repo = _repo(*articles)
    # only article[1] raises; articles 0, 2, 3 should still be analyzed
    provider = MockProvider(raise_for_ids={articles[1].id})
    svc = AnalysisService(repo=repo)
    r = svc.analyze(provider)
    assert r.analyzed_count == 3
    assert r.failed_count == 1


def test_failed_article_score_not_persisted():
    a = _article(1)
    repo = _repo(a)
    provider = MockProvider(raise_for_ids={a.id})
    svc = AnalysisService(repo=repo)
    svc.analyze(provider)
    assert repo.get_bias_score(a.id) is None


# ---------------------------------------------------------------------------
# Provider returns wrong article_id → skipped, not persisted
# ---------------------------------------------------------------------------

def test_mismatched_article_id_increments_skipped_count():
    a = _article(1)
    repo = _repo(a)
    provider = MockProvider(wrong_id_for={a.id})
    svc = AnalysisService(repo=repo)
    r = svc.analyze(provider)
    assert r.skipped_count == 1
    assert r.analyzed_count == 0


def test_mismatched_score_not_persisted():
    a = _article(1)
    repo = _repo(a)
    provider = MockProvider(wrong_id_for={a.id})
    svc = AnalysisService(repo=repo)
    svc.analyze(provider)
    assert repo.get_bias_score(a.id) is None


def test_mismatched_skip_error_message_contains_article_id():
    a = _article(1)
    repo = _repo(a)
    provider = MockProvider(wrong_id_for={a.id})
    svc = AnalysisService(repo=repo)
    r = svc.analyze(provider)
    assert any(a.id in e for e in r.errors)


# ---------------------------------------------------------------------------
# Mixed batch: some succeed, some fail, some skip
# ---------------------------------------------------------------------------

def test_mixed_batch_counts_add_up():
    a_ok1, a_ok2, a_fail, a_skip = _article(1), _article(2), _article(3), _article(4)
    repo = _repo(a_ok1, a_ok2, a_fail, a_skip)
    provider = MockProvider(
        raise_for_ids={a_fail.id},
        wrong_id_for={a_skip.id},
    )
    svc = AnalysisService(repo=repo)
    r = svc.analyze(provider)
    assert r.analyzed_count == 2
    assert r.failed_count == 1
    assert r.skipped_count == 1
    assert len(r.errors) == 2  # one per failure/skip


# ---------------------------------------------------------------------------
# SelectionParams forwarded correctly
# ---------------------------------------------------------------------------

def test_limit_param_restricts_analyzed_count():
    articles = [_article(i) for i in range(10)]
    svc = AnalysisService(repo=_repo(*articles))
    r = svc.analyze(MockProvider(), params=SelectionParams(limit=3))
    assert r.analyzed_count == 3


def test_limit_param_only_persists_limited_scores():
    articles = [_article(i) for i in range(10)]
    repo = _repo(*articles)
    svc = AnalysisService(repo=repo)
    svc.analyze(MockProvider(), params=SelectionParams(limit=4))
    scored = [a for a in articles if repo.get_bias_score(a.id) is not None]
    assert len(scored) == 4


def test_source_param_restricts_to_matching_source():
    bbc = [_article(i, source="bbc") for i in range(3)]
    cnn = [_article(i + 10, source="cnn") for i in range(3)]
    repo = _repo(*bbc, *cnn)
    svc = AnalysisService(repo=repo)
    r = svc.analyze(MockProvider(), params=SelectionParams(source="bbc"))
    assert r.analyzed_count == 3
    assert all(repo.get_bias_score(a.id) is not None for a in bbc)
    assert all(repo.get_bias_score(a.id) is None for a in cnn)


def test_analyze_with_none_params_uses_all_unscored():
    articles = [_article(i) for i in range(5)]
    svc = AnalysisService(repo=_repo(*articles))
    r = svc.analyze(MockProvider(), params=None)
    assert r.analyzed_count == 5


# ---------------------------------------------------------------------------
# MockProvider receives correct Article objects
# ---------------------------------------------------------------------------

def test_provider_called_with_correct_articles():
    a1, a2 = _article(1), _article(2)
    repo = _repo(a1, a2)
    provider = MockProvider()
    svc = AnalysisService(repo=repo)
    svc.analyze(provider)
    called_ids = {a.id for a in provider.calls}
    assert called_ids == {a1.id, a2.id}


def test_provider_not_called_for_already_scored_articles():
    a1, a2 = _article(1), _article(2)
    repo = _repo(a1, a2)
    repo.upsert_bias_score(_make_score(a1))  # a1 already scored
    provider = MockProvider()
    svc = AnalysisService(repo=repo)
    svc.analyze(provider)
    assert len(provider.calls) == 1
    assert provider.calls[0].id == a2.id
