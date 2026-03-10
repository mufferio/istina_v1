"""
Repository interfaces (abstract base classes / protocols).

Defines:
- The contract for storing and retrieving entities like Article, Conflict, BiasScore.

Typical methods:
- add_article(article), get_article(id), list_articles(...)
- upsert_bias_score(score), get_bias_score(article_id)
- add_conflict(conflict), get_conflict(id), list_conflicts()
- optional: search/filter by source/date/conflict_id

Rules:
- No file/network logic here.
- Keep methods small and use-case driven.
- Return domain entities, not raw dicts.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterable, Optional, List, Tuple

from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore



class BaseRepository(ABC):
    """
    
    Persistence contract for Istina.

    Services should depend on this interface, not on a concrete storage backend.
    Implementations may store data in memory, files, SQLite, Postgres, etc.

    Conventions:
    - article_id is the stable identifier for Articles (computed from url/source/published_at).
    - a BiasScore is uniquely identified by its article_id and provider.
    
    """

    @abstractmethod
    def add_articles(self, article: Article) -> Tuple[int, int]:
        """Add a new Article to the repository."""
        pass

    @abstractmethod
    def get_article(self, article_id: str) -> Optional[Article]:
        """Retrieve an Article by its id."""
        pass

    @abstractmethod
    def list_articles(self, limit: Optional[int] = None, source: Optional[str] = None, since: Optional[datetime] = None) -> List[Article]:
        """
        List articles with optional filtering.

        Filtering:
        - If source is provided, return only articles whose source/provider matches exactly.
        - If since is provided, return only articles with published_at >= since.
          (If your Article stores published_at as ISO string, concrete repo should parse/compare reliably.)

        Ordering:
        - Return articles in DESCENDING published_at order (newest first).
          If published_at is missing, define a consistent fallback ordering in the implementation.

        Limit:
        - If limit is provided, return at most limit articles.

        Returns:
            list[Article]
        """
        pass

    @abstractmethod
    def upsert_bias_score(self, score: BiasScore) -> None:
        """
        Insert or update a BiasScore for an article.

        Uniqueness:
        - BiasScore is keyed by article_id (one score per article_id).

        Upsert behavior:
        - If no score exists for score.article_id, insert it.
        - If one already exists, replace it (or update it) deterministically.
          Concrete repo should treat this operation as idempotent.

        Returns:
            None
        """
        pass

    @abstractmethod
    def get_bias_score(self, article_id: str, provider: Optional[str] = None) -> Optional[BiasScore]:
        """
        Fetch the BiasScore for an article_id.

        ``provider`` is accepted for forward-compatibility but is currently
        unused by all implementations — scores are keyed by ``article_id`` alone
        (one score per article, latest write wins).

        Returns:
            BiasScore if found, otherwise None.
        """
        pass