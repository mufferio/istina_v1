"""
SummarizeCommand tests.

Covers:
- execute() returns CommandResult[str]
- summary mode: output contains article counts
- summary mode: output includes bias distribution when scores present
- summary mode: output includes source breakdown
- full mode: output contains article titles
- full mode: output contains bias labels when scored
- full mode: marks unscored articles as NOT ANALYZED
- article_id filter scopes full report to a single article
- source filter scopes output to matching source
- invalid mode raises ValueError at construction
- empty repo returns a valid string (not an error)
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from istina.controller.commands.base_command import CommandResult
from istina.controller.commands.summarize import SummarizeCommand
from istina.controller.services.report_service import ReportService
from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.providers.mock_provider import MockProvider
from istina.model.repositories.memory_repository import MemoryRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _article(n: int, source: str = "Test Source", title: str = "") -> Article:
    return Article.create(
        title=title or f"Article number {n} with a real title",
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


def _repo_with(*articles: Article, scores: bool = False) -> MemoryRepository:
    repo = MemoryRepository()
    repo.add_articles(articles)
    if scores:
        for a in articles:
            repo.upsert_bias_score(_score(a))
    return repo


def _summary_cmd(repo: MemoryRepository, **kwargs) -> SummarizeCommand:
    return SummarizeCommand(service=ReportService(repo=repo), mode="summary", **kwargs)


def _full_cmd(repo: MemoryRepository, **kwargs) -> SummarizeCommand:
    return SummarizeCommand(service=ReportService(repo=repo), mode="full", **kwargs)


# ---------------------------------------------------------------------------
# Construction guards
# ---------------------------------------------------------------------------

def test_invalid_mode_raises():
    repo = MemoryRepository()
    with pytest.raises(ValueError, match="Invalid report mode"):
        SummarizeCommand(service=ReportService(repo=repo), mode="invalid")  # type: ignore


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

def test_execute_returns_command_result():
    result = _summary_cmd(_repo_with()).execute()
    assert isinstance(result, CommandResult)


def test_execute_data_is_string():
    result = _summary_cmd(_repo_with()).execute()
    assert isinstance(result.data, str)


def test_execute_success_is_true():
    assert _summary_cmd(_repo_with()).execute().success is True


def test_execute_message_equals_data():
    result = _summary_cmd(_repo_with()).execute()
    assert result.message == result.data


# ---------------------------------------------------------------------------
# Summary mode — counts
# ---------------------------------------------------------------------------

def test_summary_contains_total_article_count():
    articles = [_article(i) for i in range(5)]
    result = _summary_cmd(_repo_with(*articles)).execute()
    assert "5" in result.data


def test_summary_contains_analyzed_count():
    articles = [_article(i) for i in range(4)]
    repo = _repo_with(*articles, scores=True)
    result = _summary_cmd(repo).execute()
    assert "4" in result.data


def test_summary_zero_analyzed_when_no_scores():
    articles = [_article(i) for i in range(3)]
    result = _summary_cmd(_repo_with(*articles)).execute()
    assert "0 / 3" in result.data


# ---------------------------------------------------------------------------
# Summary mode — bias distribution
# ---------------------------------------------------------------------------

def test_summary_includes_bias_distribution_when_scored():
    articles = [_article(i) for i in range(3)]
    repo = _repo_with(*articles, scores=True)
    result = _summary_cmd(repo).execute()
    # MockProvider / stub scores used in _score() use "center"
    assert "center" in result.data


# ---------------------------------------------------------------------------
# Summary mode — source breakdown
# ---------------------------------------------------------------------------

def test_summary_includes_source_names():
    bbc = [_article(i, source="BBC News") for i in range(2)]
    cnn = [_article(i + 10, source="CNN") for i in range(2)]
    repo = _repo_with(*bbc, *cnn)
    result = _summary_cmd(repo).execute()
    assert "BBC News" in result.data
    assert "CNN" in result.data


# ---------------------------------------------------------------------------
# Full mode — article titles and labels
# ---------------------------------------------------------------------------

def test_full_mode_contains_article_title():
    a = _article(1, title="Exclusive: Climate Scientists Report Record High")
    repo = _repo_with(a)
    result = _full_cmd(repo).execute()
    assert "Exclusive: Climate Scientists Report Record High" in result.data


def test_full_mode_contains_bias_label_when_scored():
    a = _article(1)
    repo = _repo_with(a)
    repo.upsert_bias_score(_score(a, label="left"))
    result = _full_cmd(repo).execute()
    assert "left" in result.data


def test_full_mode_marks_unscored_as_not_analyzed():
    a = _article(1)
    repo = _repo_with(a)
    result = _full_cmd(repo).execute()
    assert "NOT ANALYZED" in result.data


def test_full_mode_multiple_articles_all_present():
    articles = [_article(i) for i in range(3)]
    repo = _repo_with(*articles)
    result = _full_cmd(repo).execute()
    for a in articles:
        assert a.title in result.data


# ---------------------------------------------------------------------------
# Full mode — article_id filter
# ---------------------------------------------------------------------------

def test_article_id_filter_scopes_to_single_article():
    a1 = _article(1, title="First Article Title")
    a2 = _article(2, title="Second Article Title")
    repo = _repo_with(a1, a2)
    result = _full_cmd(repo, article_id=a1.id).execute()
    assert "First Article Title" in result.data
    assert "Second Article Title" not in result.data


def test_article_id_not_found_returns_no_articles_string():
    repo = _repo_with()
    result = _full_cmd(repo, article_id="nonexistent-id").execute()
    assert result.success is True
    assert "No articles" in result.data


# ---------------------------------------------------------------------------
# Source filter
# ---------------------------------------------------------------------------

def test_summary_source_filter_restricts_output():
    bbc = [_article(i, source="bbc") for i in range(3)]
    cnn = [_article(i + 10, source="cnn") for i in range(3)]
    repo = _repo_with(*bbc, *cnn)
    result = _summary_cmd(repo, source="bbc").execute()
    assert "3" in result.data
    assert "cnn" not in result.data.lower()


# ---------------------------------------------------------------------------
# Empty repo
# ---------------------------------------------------------------------------

def test_summary_empty_repo_returns_valid_string():
    result = _summary_cmd(_repo_with()).execute()
    assert result.success is True
    assert isinstance(result.data, str)
    assert "0" in result.data


def test_full_empty_repo_returns_no_articles_string():
    result = _full_cmd(_repo_with()).execute()
    assert result.success is True
    assert "No articles" in result.data
