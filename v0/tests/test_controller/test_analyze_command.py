"""
AnalyzeCommand tests.

Covers:
- execute() returns CommandResult[AnalyzeResult]
- MockProvider produces BiasScores for unscored articles
- scores are persisted to the repo after execute()
- analyzed_count matches number of unscored articles
- SelectionParams.limit forwards correctly
- SelectionParams.source forwards correctly
- already-scored articles are skipped (analyzed_count=0 on second run)
- message string contains analyzed/skipped/failed counts
- provider failure increments failed_count and is recorded in data.errors
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

import pytest

from istina.controller.commands.analyze import AnalyzeCommand
from istina.controller.commands.base_command import CommandResult
from istina.controller.services.analysis_service import AnalyzeResult, AnalysisService, SelectionParams
from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.providers.mock_provider import MockProvider
from istina.model.repositories.memory_repository import MemoryRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _article(n: int, source: str = "test") -> Article:
    return Article.create(
        title=f"Article {n}",
        url=f"https://example.com/{n}",
        source=source,
    )


def _repo(*articles: Article) -> MemoryRepository:
    repo = MemoryRepository()
    repo.add_articles(articles)
    return repo


def _cmd(
    repo: MemoryRepository,
    provider=None,
    params: Optional[SelectionParams] = None,
) -> AnalyzeCommand:
    if provider is None:
        provider = MockProvider()
    return AnalyzeCommand(
        service=AnalysisService(repo=repo),
        visitor_or_provider=provider,
        params=params,
    )


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

def test_execute_returns_command_result():
    result = _cmd(_repo()).execute()
    assert isinstance(result, CommandResult)


def test_execute_data_is_analyze_result():
    result = _cmd(_repo()).execute()
    assert isinstance(result.data, AnalyzeResult)


def test_execute_success_is_true():
    assert _cmd(_repo()).execute().success is True


def test_execute_message_is_string():
    msg = _cmd(_repo(_article(1))).execute().message
    assert isinstance(msg, str) and len(msg) > 0


# ---------------------------------------------------------------------------
# MockProvider produces BiasScores
# ---------------------------------------------------------------------------

def test_analyzed_count_equals_unscored_articles():
    articles = [_article(i) for i in range(5)]
    result = _cmd(_repo(*articles)).execute()
    assert result.data.analyzed_count == 5


def test_scores_persisted_after_execute():
    articles = [_article(i) for i in range(3)]
    repo = _repo(*articles)
    _cmd(repo).execute()
    for a in articles:
        assert repo.get_bias_score(a.id) is not None


def test_persisted_scores_are_bias_score_instances():
    a = _article(1)
    repo = _repo(a)
    _cmd(repo).execute()
    assert isinstance(repo.get_bias_score(a.id), BiasScore)


def test_score_article_id_matches_article():
    a = _article(1)
    repo = _repo(a)
    _cmd(repo).execute()
    assert repo.get_bias_score(a.id).article_id == a.id


# ---------------------------------------------------------------------------
# Second run skips already-scored articles
# ---------------------------------------------------------------------------

def test_second_run_analyzed_count_is_zero():
    articles = [_article(i) for i in range(3)]
    repo = _repo(*articles)
    _cmd(repo).execute()
    r2 = _cmd(repo).execute()
    assert r2.data.analyzed_count == 0


# ---------------------------------------------------------------------------
# SelectionParams forwarding
# ---------------------------------------------------------------------------

def test_limit_restricts_analyzed_count():
    articles = [_article(i) for i in range(10)]
    result = _cmd(_repo(*articles), params=SelectionParams(limit=4)).execute()
    assert result.data.analyzed_count == 4


def test_source_filter_restricts_to_matching_source():
    bbc = [_article(i, source="bbc") for i in range(3)]
    cnn = [_article(i + 10, source="cnn") for i in range(3)]
    repo = _repo(*bbc, *cnn)
    result = _cmd(repo, params=SelectionParams(source="bbc")).execute()
    assert result.data.analyzed_count == 3
    for a in cnn:
        assert repo.get_bias_score(a.id) is None


# ---------------------------------------------------------------------------
# Provider failure handling
# ---------------------------------------------------------------------------

class _FailingProvider:
    """Provider that always raises."""
    def analyze_article(self, article: Article) -> BiasScore:
        raise RuntimeError("simulated failure")


def test_provider_failure_increments_failed_count():
    articles = [_article(i) for i in range(3)]
    repo = _repo(*articles)
    result = AnalyzeCommand(
        service=AnalysisService(repo=repo),
        visitor_or_provider=_FailingProvider(),
    ).execute()
    assert result.data.failed_count == 3


def test_provider_failure_errors_recorded():
    a = _article(1)
    repo = _repo(a)
    result = AnalyzeCommand(
        service=AnalysisService(repo=repo),
        visitor_or_provider=_FailingProvider(),
    ).execute()
    assert len(result.data.errors) > 0


def test_provider_failure_success_still_true():
    a = _article(1)
    repo = _repo(a)
    result = AnalyzeCommand(
        service=AnalysisService(repo=repo),
        visitor_or_provider=_FailingProvider(),
    ).execute()
    assert result.success is True


# ---------------------------------------------------------------------------
# Message content
# ---------------------------------------------------------------------------

def test_message_contains_analyzed_count():
    articles = [_article(i) for i in range(3)]
    result = _cmd(_repo(*articles)).execute()
    assert "3" in result.message


def test_message_contains_skipped_and_failed():
    result = _cmd(_repo()).execute()
    assert "Skipped" in result.message
    assert "Failed" in result.message
