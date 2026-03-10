"""
IngestCommand tests.

Covers:
- execute() returns CommandResult[IngestResults]
- articles are stored in MemoryRepository via a fake adapter
- new_count / existing_count / fetched_count are correct
- message is a populated string
- empty feeds list raises ValueError at construction
- adapter-level error is captured in data.errors (success still True)
- second ingest of same articles increments existing_count, not new_count
"""

from __future__ import annotations

from typing import List

import pytest

from istina.controller.commands.base_command import CommandResult
from istina.controller.commands.ingest import IngestCommand
from istina.controller.services.ingest_service import IngestResults, IngestService
from istina.model.entities.article import Article
from istina.model.repositories.memory_repository import MemoryRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _article(n: int, source: str = "test") -> Article:
    return Article.create(
        title=f"Article {n}",
        url=f"https://example.com/{n}",
        source=source,
    )


class _FakeAdapter:
    """Adapter stub: returns a fixed list of Articles, no network calls."""

    def __init__(self, articles: List[Article]):
        self._articles = articles

    def fetch_articles(self, urls: List[str]) -> List[Article]:
        return list(self._articles)


class _ErrorAdapter:
    """Adapter stub that always raises."""

    def fetch_articles(self, urls: List[str]) -> List[Article]:
        raise RuntimeError("simulated network failure")


def _build(articles: List[Article]) -> tuple[IngestCommand, MemoryRepository]:
    repo = MemoryRepository()
    adapter = _FakeAdapter(articles)
    service = IngestService(repo=repo, rss_adapter=adapter)
    cmd = IngestCommand(service=service, feeds=["https://fake.feed/rss"])
    return cmd, repo


# ---------------------------------------------------------------------------
# Construction guards
# ---------------------------------------------------------------------------

def test_empty_feeds_raises():
    repo = MemoryRepository()
    service = IngestService(repo=repo)
    with pytest.raises(ValueError, match="at least one feed"):
        IngestCommand(service=service, feeds=[])


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

def test_execute_returns_command_result():
    cmd, _ = _build([_article(1)])
    result = cmd.execute()
    assert isinstance(result, CommandResult)


def test_execute_data_is_ingest_results():
    cmd, _ = _build([_article(1)])
    result = cmd.execute()
    assert isinstance(result.data, IngestResults)


def test_execute_success_is_true():
    cmd, _ = _build([_article(1)])
    assert cmd.execute().success is True


def test_execute_message_is_string():
    cmd, _ = _build([_article(1)])
    msg = cmd.execute().message
    assert isinstance(msg, str) and len(msg) > 0


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------

def test_fetched_count_equals_adapter_output():
    articles = [_article(i) for i in range(5)]
    cmd, _ = _build(articles)
    assert cmd.execute().data.fetched_count == 5


def test_new_count_matches_articles_stored():
    articles = [_article(i) for i in range(3)]
    cmd, repo = _build(articles)
    result = cmd.execute()
    assert result.data.new_count == 3
    assert result.data.existing_count == 0


def test_articles_are_persisted_in_repo():
    articles = [_article(i) for i in range(4)]
    cmd, repo = _build(articles)
    cmd.execute()
    stored = repo.list_articles()
    assert len(stored) == 4


def test_second_ingest_increments_existing_count():
    articles = [_article(i) for i in range(3)]
    cmd1, repo = _build(articles)
    cmd1.execute()

    # Re-use same repo; ingest same articles again
    adapter = _FakeAdapter(articles)
    service = IngestService(repo=repo, rss_adapter=adapter)
    cmd2 = IngestCommand(service=service, feeds=["https://fake.feed/rss"])
    result = cmd2.execute()

    assert result.data.new_count == 0
    assert result.data.existing_count == 3


# ---------------------------------------------------------------------------
# Adapter error
# ---------------------------------------------------------------------------

def test_adapter_error_returns_success_true_with_errors():
    repo = MemoryRepository()
    service = IngestService(repo=repo, rss_adapter=_ErrorAdapter())
    cmd = IngestCommand(service=service, feeds=["https://fake.feed/rss"])
    result = cmd.execute()
    assert result.success is True
    assert len(result.data.errors) > 0


def test_adapter_error_fetched_count_is_zero():
    repo = MemoryRepository()
    service = IngestService(repo=repo, rss_adapter=_ErrorAdapter())
    cmd = IngestCommand(service=service, feeds=["https://fake.feed/rss"])
    assert cmd.execute().data.fetched_count == 0


def test_message_contains_new_count():
    articles = [_article(i) for i in range(6)]
    cmd, _ = _build(articles)
    msg = cmd.execute().message
    assert "6" in msg
