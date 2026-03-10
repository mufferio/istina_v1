"""
Unit tests for rss_adapter.fetch_articles (Issue 4.4).

Covers:
- Empty URL list returns empty list
- Single good feed returns its articles
- Multiple good feeds aggregate all articles
- One bad feed (AdapterError) does not abort the rest
- All bad feeds return empty list (no crash)
- ValueError from fetch_feed (bad URL) does not abort the rest
- fetch_feed failure is logged as an error
- parse_entries result (incl. empty) is handled correctly
- Source is passed as the feed URL to parse_entries
"""
from __future__ import annotations

from typing import List
from unittest.mock import call, patch

import pytest

from istina.model.adapters.adapter_error import AdapterError
from istina.model.adapters.rss_adapter import fetch_articles
from istina.model.entities.article import Article


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_article(n: int) -> Article:
    return Article.create(
        title=f"Article {n}",
        url=f"https://example.com/{n}",
        source="test-source",
    )


_XML = "<rss/>"  # placeholder — parse_xml/parse_entries are mocked in most tests


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_fetch_articles_empty_urls_returns_empty():
    assert fetch_articles([]) == []


def test_fetch_articles_single_feed_returns_articles(monkeypatch):
    articles = [_make_article(1), _make_article(2)]

    monkeypatch.setattr("istina.model.adapters.rss_adapter.fetch_feed", lambda url, **kw: _XML)
    monkeypatch.setattr("istina.model.adapters.rss_adapter.parse_xml", lambda xml: object())
    monkeypatch.setattr("istina.model.adapters.rss_adapter.parse_entries", lambda parsed, source=None: articles)

    result = fetch_articles(["https://feed1.com/rss"])
    assert result == articles


def test_fetch_articles_multiple_feeds_aggregates_all(monkeypatch):
    feed_articles = {
        "https://feed1.com/rss": [_make_article(1)],
        "https://feed2.com/rss": [_make_article(2), _make_article(3)],
        "https://feed3.com/rss": [_make_article(4)],
    }

    monkeypatch.setattr("istina.model.adapters.rss_adapter.fetch_feed", lambda url, **kw: _XML)
    monkeypatch.setattr("istina.model.adapters.rss_adapter.parse_xml", lambda xml: object())
    monkeypatch.setattr(
        "istina.model.adapters.rss_adapter.parse_entries",
        lambda parsed, source=None: feed_articles[source],
    )

    result = fetch_articles(list(feed_articles.keys()))
    assert len(result) == 4
    assert result == [_make_article(1), _make_article(2), _make_article(3), _make_article(4)]


def test_fetch_articles_feed_with_no_entries_contributes_nothing(monkeypatch):
    monkeypatch.setattr("istina.model.adapters.rss_adapter.fetch_feed", lambda url, **kw: _XML)
    monkeypatch.setattr("istina.model.adapters.rss_adapter.parse_xml", lambda xml: object())
    monkeypatch.setattr("istina.model.adapters.rss_adapter.parse_entries", lambda parsed, source=None: [])

    result = fetch_articles(["https://feed1.com/rss"])
    assert result == []


# ---------------------------------------------------------------------------
# Fault-tolerance: one bad feed must not stop the rest
# ---------------------------------------------------------------------------

def test_fetch_articles_adapter_error_skips_feed_continues(monkeypatch):
    good_articles = [_make_article(99)]
    call_count = {"n": 0}

    def fake_fetch(url, **kw):
        call_count["n"] += 1
        if "bad" in url:
            raise AdapterError("simulated failure")
        return _XML

    monkeypatch.setattr("istina.model.adapters.rss_adapter.fetch_feed", fake_fetch)
    monkeypatch.setattr("istina.model.adapters.rss_adapter.parse_xml", lambda xml: object())
    monkeypatch.setattr("istina.model.adapters.rss_adapter.parse_entries", lambda parsed, source=None: good_articles)

    result = fetch_articles(["https://bad-feed.com/rss", "https://good-feed.com/rss"])

    assert result == good_articles          # bad feed skipped, good feed contributed
    assert call_count["n"] == 2             # both URLs were attempted


def test_fetch_articles_value_error_skips_feed_continues(monkeypatch):
    """ValueError from fetch_feed (e.g. empty URL) must also not abort the run."""
    good_articles = [_make_article(7)]

    def fake_fetch(url, **kw):
        if "bad" in url:
            raise ValueError("url must be a non-empty string")
        return _XML

    monkeypatch.setattr("istina.model.adapters.rss_adapter.fetch_feed", fake_fetch)
    monkeypatch.setattr("istina.model.adapters.rss_adapter.parse_xml", lambda xml: object())
    monkeypatch.setattr("istina.model.adapters.rss_adapter.parse_entries", lambda parsed, source=None: good_articles)

    result = fetch_articles(["https://bad-feed.com/rss", "https://good-feed.com/rss"])
    assert result == good_articles


def test_fetch_articles_all_feeds_fail_returns_empty(monkeypatch):
    monkeypatch.setattr(
        "istina.model.adapters.rss_adapter.fetch_feed",
        lambda url, **kw: (_ for _ in ()).throw(AdapterError("fail")),
    )

    result = fetch_articles(["https://a.com/rss", "https://b.com/rss"])
    assert result == []


def test_fetch_articles_parse_entries_exception_skips_feed(monkeypatch):
    """Even if parse_entries itself raises, the next feed is still processed."""
    good_articles = [_make_article(5)]
    call_count = {"n": 0}

    monkeypatch.setattr("istina.model.adapters.rss_adapter.fetch_feed", lambda url, **kw: _XML)
    monkeypatch.setattr("istina.model.adapters.rss_adapter.parse_xml", lambda xml: object())

    def fake_parse_entries(parsed, source=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("unexpected parse failure")
        return good_articles

    monkeypatch.setattr("istina.model.adapters.rss_adapter.parse_entries", fake_parse_entries)

    result = fetch_articles(["https://feed1.com/rss", "https://feed2.com/rss"])
    assert result == good_articles


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def test_fetch_articles_logs_error_on_feed_failure(monkeypatch, caplog):
    import logging

    monkeypatch.setattr(
        "istina.model.adapters.rss_adapter.fetch_feed",
        lambda url, **kw: (_ for _ in ()).throw(AdapterError("boom")),
    )

    with caplog.at_level(logging.ERROR, logger="istina.model.adapters.rss_adapter"):
        fetch_articles(["https://failing-feed.com/rss"])

    assert any("failing-feed.com" in r.message for r in caplog.records)
    assert any(r.levelno == logging.ERROR for r in caplog.records)


# ---------------------------------------------------------------------------
# Source forwarding
# ---------------------------------------------------------------------------

def test_fetch_articles_passes_url_as_source_to_parse_entries(monkeypatch):
    """fetch_articles must forward the feed URL as the source argument."""
    captured = {}

    monkeypatch.setattr("istina.model.adapters.rss_adapter.fetch_feed", lambda url, **kw: _XML)
    monkeypatch.setattr("istina.model.adapters.rss_adapter.parse_xml", lambda xml: object())

    def fake_parse_entries(parsed, source=None):
        captured["source"] = source
        return []

    monkeypatch.setattr("istina.model.adapters.rss_adapter.parse_entries", fake_parse_entries)

    fetch_articles(["https://specific-feed.com/rss"])
    assert captured["source"] == "https://specific-feed.com/rss"
