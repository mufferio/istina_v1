"""
IngestService (use case).

Workflow:
1) Accept feed URLs.
2) Use RSSAdapter to fetch/parse -> List[Article].
3) Store articles via repository (dedupe by id).
4) Return ingestion result (counts, new vs existing).

Notes:
- Keep deduplication logic here (or in repo) but make it consistent.
- Should be easy to test with MemoryRepository + mocked RSSAdapter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from istina.model.repositories.base_repository import BaseRepository


class RSSAdapterWrapper:
    def fetch_articles(self, urls):
        from istina.model.adapters.rss_adapter import fetch_articles
        return fetch_articles(urls)


@dataclass
class IngestResults:
    fetched_count: int
    new_count: int
    existing_count: int
    errors: List[str] = field(default_factory=list)


class IngestService:
    """
    Use-case service: ingest RSS feeds into the repository.

    It does NOT do HTTP or parsing itself (adapter handles that).
    It does NOT know storage details (repo handles that).

    It returns counts that the CLI can display.
    """

    def __init__(self, repo: BaseRepository, rss_adapter: Optional[RSSAdapterWrapper] = None):
        self.repo = repo
        self.rss_adapter = rss_adapter or RSSAdapterWrapper()

    def ingest(self, feeds: List[str]) -> IngestResults:
        """
        Ingest a set of RSS feed URLs.

        Steps:
        1) adapter.fetch_articles(feeds) -> list[Article]
        2) repo.add_articles(articles) -> (new_count, existing_count)
        3) return IngestResults with fetched_count + counts + errors

        Behavior:
        - If the adapter raises, we return errors and do not crash the CLI.
        """
        errors: List[str] = []

        try:
            articles = self.rss_adapter.fetch_articles(feeds)
        except Exception as e:
            # v0: capture error and continue gracefully
            return IngestResults(
                fetched_count=0,
                new_count=0,
                existing_count=0,
                errors=[str(e)],
            )
        
        fetched_count = len(articles)   

        try:
            new_count, existing_count = self.repo.add_articles(articles)
        except Exception as e:
            # if repo fails, surface cleanly
            return IngestResults(
                fetched_count=fetched_count,
                new_count=0,
                existing_count=0,
                errors=[str(e)],
            )

        return IngestResults(
            fetched_count=fetched_count,
            new_count=new_count,
            existing_count=existing_count,
            errors=errors,
        )
     