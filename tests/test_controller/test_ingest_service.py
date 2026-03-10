"""
Unit tests for IngestService (Issue 5 — ingest_service.py).

Covers:
- Constructor accepts repo + rss_adapter
- ingest() returns IngestResults with correct field names
- fetched_count matches articles returned by the adapter
- new_count / existing_count come from repo.add_articles
- Adapter failure is caught, errors list is populated, counts are 0
- Repo failure is caught, errors list is populated, fetched_count preserved
- Empty feed list returns zero counts and no errors
- All-duplicate feed returns fetched_count > 0, new_count == 0
- Custom rss_adapter is used (not the default wrapper)
- Default rss_adapter (RSSAdapterWrapper) is created when none supplied
"""
from __future__ import annotations

from typing import List, Sequence, Tuple
from unittest.mock import MagicMock

import pytest

from istina.controller.services.ingest_service import IngestResults, IngestService
from istina.model.entities.article import Article
from istina.model.repositories.memory_repository import MemoryRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _article(n: int) -> Article:
    return Article.create(
        title=f"Article {n}",
        url=f"https://example.com/{n}",
        source="test",
    )


class _FakeAdapter:
    """Controllable stand-in for RSSAdapterWrapper."""

    def __init__(self, articles: List[Article] = (), raise_with: Exception = None):
        self._articles = list(articles)
        self._raise = raise_with
        self.called_with: Sequence[str] = []

    def fetch_articles(self, urls: Sequence[str]) -> List[Article]:
        self.called_with = list(urls)
        if self._raise:
            raise self._raise
        return self._articles


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

def test_constructor_accepts_repo_and_adapter():
    repo = MemoryRepository()
    adapter = _FakeAdapter()
    svc = IngestService(repo=repo, rss_adapter=adapter)
    assert svc.repo is repo
    assert svc.rss_adapter is adapter


def test_constructor_creates_default_adapter_when_none_given():
    from istina.controller.services.ingest_service import RSSAdapterWrapper
    svc = IngestService(repo=MemoryRepository())
    assert isinstance(svc.rss_adapter, RSSAdapterWrapper)


# ---------------------------------------------------------------------------
# Return type & field names
# ---------------------------------------------------------------------------

def test_ingest_returns_ingest_results_instance():
    svc = IngestService(repo=MemoryRepository(), rss_adapter=_FakeAdapter())
    result = svc.ingest([])
    assert isinstance(result, IngestResults)


def test_ingest_result_has_required_fields():
    svc = IngestService(repo=MemoryRepository(), rss_adapter=_FakeAdapter())
    result = svc.ingest([])
    assert hasattr(result, "fetched_count")
    assert hasattr(result, "new_count")
    assert hasattr(result, "existing_count")
    assert hasattr(result, "errors")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_ingest_empty_url_list_returns_zero_counts():
    svc = IngestService(repo=MemoryRepository(), rss_adapter=_FakeAdapter(articles=[]))
    r = svc.ingest([])
    assert r.fetched_count == 0
    assert r.new_count == 0
    assert r.existing_count == 0
    assert r.errors == []


def test_ingest_fetched_count_matches_adapter_output():
    articles = [_article(i) for i in range(5)]
    svc = IngestService(repo=MemoryRepository(), rss_adapter=_FakeAdapter(articles=articles))
    r = svc.ingest(["https://feed.com/rss"])
    assert r.fetched_count == 5


def test_ingest_new_count_reflects_repo_dedup():
    articles = [_article(i) for i in range(3)]
    svc = IngestService(repo=MemoryRepository(), rss_adapter=_FakeAdapter(articles=articles))
    r = svc.ingest(["https://feed.com/rss"])
    assert r.new_count == 3
    assert r.existing_count == 0
    assert r.errors == []


def test_ingest_second_run_counts_as_existing():
    articles = [_article(1), _article(2)]
    repo = MemoryRepository()
    adapter = _FakeAdapter(articles=articles)
    svc = IngestService(repo=repo, rss_adapter=adapter)

    r1 = svc.ingest(["https://feed.com/rss"])
    assert r1.new_count == 2 and r1.existing_count == 0

    r2 = svc.ingest(["https://feed.com/rss"])
    assert r2.new_count == 0
    assert r2.existing_count == 2
    assert r2.fetched_count == 2


def test_ingest_passes_urls_to_adapter():
    adapter = _FakeAdapter()
    svc = IngestService(repo=MemoryRepository(), rss_adapter=adapter)
    urls = ["https://a.com/rss", "https://b.com/rss"]
    svc.ingest(urls)
    assert adapter.called_with == urls


# ---------------------------------------------------------------------------
# Error handling — adapter failure
# ---------------------------------------------------------------------------

def test_ingest_adapter_error_returns_zero_counts_with_error_message():
    adapter = _FakeAdapter(raise_with=RuntimeError("network down"))
    svc = IngestService(repo=MemoryRepository(), rss_adapter=adapter)
    r = svc.ingest(["https://feed.com/rss"])
    assert r.fetched_count == 0
    assert r.new_count == 0
    assert r.existing_count == 0
    assert len(r.errors) == 1
    assert "network down" in r.errors[0]


def test_ingest_adapter_error_does_not_raise():
    adapter = _FakeAdapter(raise_with=Exception("boom"))
    svc = IngestService(repo=MemoryRepository(), rss_adapter=adapter)
    # Must not propagate
    r = svc.ingest(["https://feed.com/rss"])
    assert isinstance(r, IngestResults)


# ---------------------------------------------------------------------------
# Error handling — repo failure
# ---------------------------------------------------------------------------

def test_ingest_repo_error_preserves_fetched_count():
    articles = [_article(1), _article(2)]
    adapter = _FakeAdapter(articles=articles)

    broken_repo = MagicMock(spec=MemoryRepository)
    broken_repo.add_articles.side_effect = IOError("disk full")

    svc = IngestService(repo=broken_repo, rss_adapter=adapter)
    r = svc.ingest(["https://feed.com/rss"])

    assert r.fetched_count == 2   # adapter succeeded
    assert r.new_count == 0
    assert r.existing_count == 0
    assert "disk full" in r.errors[0]


def test_ingest_repo_error_does_not_raise():
    adapter = _FakeAdapter(articles=[_article(1)])
    broken_repo = MagicMock(spec=MemoryRepository)
    broken_repo.add_articles.side_effect = RuntimeError("db gone")

    svc = IngestService(repo=broken_repo, rss_adapter=adapter)
    r = svc.ingest(["https://feed.com/rss"])
    assert isinstance(r, IngestResults)
