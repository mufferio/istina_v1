"""
RSS Adapter.

Purpose:
- Fetch and parse RSS feeds into Article entities.

Responsibilities:
- Accept feed URLs (single or list)
- Fetch content (requests/httpx)
- Parse RSS (feedparser)
- Map feed entries -> Article
- Handle errors:
  - unreachable feeds
  - malformed entries
  - missing fields

Output:
- List[Article] ready to be stored by repositories.

Future:
- Add caching, ETags, incremental fetching, more sources (APIs).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence

import feedparser
import requests

from istina.model.adapters.adapter_error import AdapterError
from istina.model.entities.article import Article
from istina.utils.retry import retry

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10  # seconds


def fetch_feed(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """
    Fetch RSS XML reliably from a feed URL.

    Requirements (Issue 4.2):
    - Uses HTTP via requests
    - Uses a timeout (default 10s)
    - Non-200 responses raise AdapterError
    - Integrates retry() for transient network failures (timeouts / connection errors)

    Returns:
        Response text (RSS XML) as a non-empty string.

    Raises:
        AdapterError: on non-200 responses, empty body, or any final failure after retries.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url must be a non-empty string")

    url = url.strip()

    def _do_request() -> str:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code != 200:
            raise AdapterError(f"Failed to fetch feed: {url} (status code: {resp.status_code})")

        text = resp.text or ""
        if not text.strip():
            raise AdapterError(f"Empty response body for feed: {url}")

        return text

    try:
        return retry(
            _do_request,
            exceptions=(requests.RequestException, AdapterError),
            max_attempts=3,
            base_delay=0.0,
            backoff_factor=2.0,
        )
    except AdapterError:
        raise
    except Exception as e:
        raise AdapterError(f"Failed to fetch feed after retries: {url} (error: {e})") from e


def _to_iso8601_utc(entry: Any) -> Optional[str]:
    """
    Convert feedparser date fields into an ISO-8601 UTC string if available.

    feedparser commonly provides `published_parsed` or `updated_parsed`
    as time.struct_time in UTC. Returns None if neither is available or parseable.
    """
    t = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not t:
        return None
    try:
        dt = datetime(*t[:6], tzinfo=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    except Exception:
        return None


def parse_xml(xml: str) -> Any:
    """
    Parse RSS/Atom XML string into a feedparser result object.
    Separated from parse_entries for testability.
    """
    return feedparser.parse(xml)


def parse_entries(parsed: Any, source: Optional[str] = None) -> List[Article]:
    """
    Convert parsed feed entries into Article domain entities safely.

    Requirements (Issue 4.3):
    - Map entry -> Article fields (title/url/source/published_at/summary)
    - Handle missing optional fields gracefully
    - Use Article.create() for stable ID computation
    - Skip + log bad entries without crashing the whole batch

    Args:
        parsed: feedparser.parse(...) result (has .entries and .feed metadata).
        source: optional override for Article.source;
                defaults to feed title, feed link, or "rss" if unavailable.

    Returns:
        List[Article] — may be empty if all entries fail validation.
    """
    articles: List[Article] = []

    # Resolve source label: explicit override > feed title > feed link > fallback
    feed_source: str
    if source is not None:
        feed_source = source
    else:
        feed = getattr(parsed, "feed", {}) or {}
        feed_source = feed.get("title") or feed.get("link") or "rss"

    for entry in getattr(parsed, "entries", []) or []:
        try:
            title = (getattr(entry, "title", None) or "").strip()
            url = (getattr(entry, "link", None) or "").strip()

            if not title or not url:
                raise ValueError(f"missing required field(s): title={title!r}, url={url!r}")

            summary_raw = (
                getattr(entry, "summary", None)
                or getattr(entry, "description", None)
                or ""
            )
            summary = summary_raw.strip() or None
            published_at = _to_iso8601_utc(entry)

            article = Article.create(
                title=title,
                url=url,
                source=str(feed_source),
                published_at=published_at,
                summary=summary,
            )
            articles.append(article)

        except Exception as e:
            logger.warning("Skipping bad feed entry: %s", e, exc_info=False)
            continue

    return articles


def fetch_articles(urls: Sequence[str]) -> List[Article]:
    """
    Fetch articles from multiple RSS feed URLs and return a combined list.

    Requirements (Issue 4.4):
    - For each URL: fetch_feed -> parse_xml -> parse_entries
    - One failing feed must not abort the rest (log the error, continue)
    - Aggregate articles across all successfully processed feeds

    Args:
        urls: sequence of RSS feed URLs to ingest.

    Returns:
        Combined List[Article] from all feeds that succeeded.
        May be empty if every feed fails.
    """
    results: List[Article] = []

    for url in urls:
        try:
            xml = fetch_feed(url)
            parsed = parse_xml(xml)
            # Pass the URL as the source fallback so articles from a feed with no
            # title/link metadata are still identifiable by their origin URL.
            articles = parse_entries(parsed, source=url)
            results.extend(articles)
        except Exception as e:
            logger.error("RSS feed failed url=%s error=%s", url, e, exc_info=False)
            continue

    return results


