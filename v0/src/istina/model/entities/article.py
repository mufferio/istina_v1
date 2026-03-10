"""
Article entity.

Represents:
- A single news item (from RSS or other sources).

Typical fields:
- id: stable unique id (hash of url/title+source+published_at)
- title, url, source, published_at
- author (optional), summary/description (optional)
- content_text (optional; may be fetched later)
- conflict_id (optional; later: clustering/assignment)
- bias_score (optional; later: attached analysis result)
- raw: original feed payload for debugging/auditing (optional)

Rules/validation:
- url and title should not be empty.
- published_at should be timezone-aware or consistently naive (pick one).
- Provide helper methods for stable id computation and serialization.

Used by:
- adapters/rss_adapter.py to create Article objects from feeds
- repositories to store/load Articles
- visitors to run analysis operations over Articles
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Mapping
import hashlib


def _norm(s: Optional[str]) -> str:
    """Normalize strings for stable hashing."""
    if s is None:
        return ""
    return " ".join(s.strip().split()).lower()


def _norm_url(url: str) -> str:
    """Normalize URLs for dedupe hashing (basic normalization)."""
    u = url.strip()
    if u.endswith("/"):
        u = u[:-1]
    return u

@dataclass(frozen=True)
class Article:
    """
    Core news Article entity.

    - Immutable (frozen dataclass)
    - Stable id computed from source, url, published_at
    - Used across ingestion, storage, analysis, and reporting
    """
    id: str
    title: str
    url: str
    source: str
    published_at: Optional[str] = None  # ISO 8601 string, e.g. "2026-02-17T12:30:00Z"
    summary: Optional[str] = None

    @staticmethod
    def compute_id(*, url: str, source: str, published_at: Optional[str]) -> str:
        key = f"{_norm(source)}|{_norm_url(url)}|{_norm(published_at)}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    @classmethod
    def create(
        cls,
        *,
        title: str,
        url: str,
        source: str,
        published_at: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> "Article":
        if not isinstance(url, str):
            raise ValueError("Article.url must be a string")
        if not isinstance(source, str):
            raise ValueError("Article.source must be a string")
        if not isinstance(title, str):
            raise ValueError("Article.title must be a string")
        if not url or not url.strip():
            raise ValueError("Article.url is required")
        if not source or not source.strip():
            raise ValueError("Article.source is required")
        if not title or not title.strip():
            raise ValueError("Article.title is required")

        aid = cls.compute_id(url=url, source=source, published_at=published_at)
        return cls(
            id=aid,
            title=title.strip(),
            url=_norm_url(url),
            source=source.strip(),
            published_at=published_at.strip() if isinstance(published_at, str) else None,
            summary=summary.strip() if isinstance(summary, str) else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "published_at": self.published_at,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Article":
        try:
            title = d["title"]
            url = d["url"]
            source = d["source"]
        except KeyError as e:
            raise ValueError(f"Missing required field: {e.args[0]}") from None

        a = cls.create(
            title=title,
            url=url,
            source=source,
            published_at=d.get("published_at"),
            summary=d.get("summary"),
        )

        stored_id = d.get("id")
        if stored_id is not None and stored_id != a.id:
            raise ValueError(f"Article id mismatch: stored={stored_id!r} computed={a.id!r}")

        return a




