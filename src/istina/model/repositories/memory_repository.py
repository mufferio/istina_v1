"""
In-memory repository implementation.

Purpose:
- Fast, dependency-free storage for:
  - unit tests
  - local prototyping
- Acts as the reference implementation for repository behavior.

Implementation notes:
- Use dicts keyed by id: articles[id] = Article, scores[article_id] = BiasScore
- Provide simple filtering (by source/date) if needed by services.
- Deterministic behavior for tests (no randomness, stable ordering).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.repositories.base_repository import BaseRepository

#issue-3.5: all 48 tests passed at this point 
#Date/Time: 2026-02-20, 3:15 PM

@dataclass
class MemoryRepository(BaseRepository):
    """
    in-memory repository for fast dev/testing

    Storage:
    - articles: stored in a dict keyed by article_id 
    - BiasScores: stored in a dict keyed by article_id

    Ordering Policy:
    - Deterministic: published_at DESC
    - If published_at is missing, fall back to insertion order

    """

    def __init__(self):
        self.articles: Dict[str, Article] = {}
        self._bias_scores: Dict[str, BiasScore] = {}
        # track insertion order for deterministic fallback ordering
        self._insert_index: Dict[str, int] = {}
        self._next_index = 0

    #articles ->

    def add_articles(self, articles: Iterable[Article]) -> Tuple[int, int]:
        new_count = 0
        existing_count = 0
        for a in articles:
            article_id = getattr(a, "article_id", None) or getattr(a, "id", None)
            if not article_id:
                raise ValueError("Article missing article_id/id")
            if article_id in self.articles:
                existing_count += 1
                # Policy; do not overwrite existing articles (dedupe)
                continue
            
            self.articles[article_id] = a
            self._insert_index[article_id] = self._next_index
            self._next_index += 1
            new_count += 1

        return new_count, existing_count

    # Helper for single article addition
    def _add_article(self, article: Article) -> None:
        self.add_articles([article])

    def get_article(self, article_id: str) -> Optional[Article]:
        return self.articles.get(article_id)
    

    def list_articles(
        self,
        limit: Optional[int] = None,
        source: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> List[Article]:
        items = list(self.articles.values())

        # Filtering
        if source is not None:
            items = [a for a in items if a.source == source]
        
        if since is not None:
            def published_at_date(a: Article) -> Optional[datetime]:
                date = self._coerce_published_at(a)
                return date
            
            items = [a for a in items if (published_at_date(a) is not None and published_at_date(a) >= since)]
        
        def sort_key(a: Article):
            article_id = getattr(a, "article_id", None) or getattr(a, "id", None)
            idx = self._insert_index.get(article_id, 10**12)

            dt = self._coerce_published_at(a)

            # put unparsable/missing dates at the end by using datetime.min
            dt_key = dt if dt is not None else datetime.min
            

            # Sort DESC by dt, ASC by insertion index
            return (dt_key, -idx)
        
        items.sort(key=sort_key, reverse=True)

        if limit is not None:
            return items[: max(0, limit)]
        return items
    
    #bias scores ->

    def upsert_bias_score(self, score: BiasScore) -> None:
        article_id = score.article_id
        if not article_id:
            raise ValueError("BiasScore missing article_id")
        self._bias_scores[article_id] = score

    
    def get_bias_score(self, article_id: str) -> Optional[BiasScore]:
        return self._bias_scores.get(article_id)
    
    # helpers ->

    def _coerce_published_at(self, article: Article) -> Optional[datetime]:
        """
        Try to interpret Article.published_at as a datetime.

        Supports:
        - datetime instance
        - ISO string (including 'Z')
        """

        val = getattr(article, "published_at", None)
        if val is None:
            return None
        
        if isinstance(val, datetime):
            return val
        
        if isinstance(val, str):
            s = val.strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            
            try:
                return datetime.fromisoformat(s)
            except Exception:
                return None
        return None

