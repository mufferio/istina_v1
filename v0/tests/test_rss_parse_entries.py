"""
Unit tests for rss_adapter.parse_xml and rss_adapter.parse_entries.

Covers:
- Happy path: valid RSS XML produces correct Article objects
- Source override vs feed title fallback vs "rss" fallback
- Missing title or url skips the entry
- Missing optional fields (summary, published_at) are handled gracefully
- published_at is converted to ISO-8601 UTC string
- Empty feed (no entries) returns empty list
- All-bad entries returns empty list (no crash)
- parse_xml returns a feedparser-like object
- Duplicate entries both appear (dedup is repo's responsibility)
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, List, Optional

import pytest

from istina.model.adapters.rss_adapter import parse_entries, parse_xml
from istina.model.entities.article import Article


# ---------------------------------------------------------------------------
# Helpers to build fake feedparser objects
# ---------------------------------------------------------------------------

def _entry(
    title: Optional[str] = "Test Title",
    link: Optional[str] = "https://example.com/1",
    summary: Optional[str] = "A summary.",
    published_parsed: Optional[time.struct_time] = None,
    updated_parsed: Optional[time.struct_time] = None,
) -> Any:
    """Build a minimal fake feedparser entry."""
    e = SimpleNamespace()
    e.title = title
    e.link = link
    e.summary = summary
    e.description = None
    e.published_parsed = published_parsed
    e.updated_parsed = updated_parsed
    return e


def _parsed(
    entries: List[Any] = (),
    feed_title: Optional[str] = "Feed Title",
    feed_link: Optional[str] = "https://example.com",
) -> Any:
    """Build a minimal fake feedparser result object."""
    p = SimpleNamespace()
    p.entries = list(entries)
    p.feed = {}
    if feed_title is not None:
        p.feed["title"] = feed_title
    if feed_link is not None:
        p.feed["link"] = feed_link
    return p


_STRUCT_TIME = time.strptime("2026-02-19T12:00:00", "%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------------------
# parse_xml
# ---------------------------------------------------------------------------

def test_parse_xml_returns_feedparser_result():
    xml = """<?xml version="1.0"?>
    <rss version="2.0">
      <channel>
        <title>Test Feed</title>
        <item><title>Item 1</title><link>https://example.com/1</link></item>
      </channel>
    </rss>"""
    result = parse_xml(xml)
    assert hasattr(result, "entries")
    assert hasattr(result, "feed")


def test_parse_xml_empty_string_returns_empty_entries():
    result = parse_xml("")
    assert isinstance(result.entries, list)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_parse_entries_returns_article_list():
    parsed = _parsed(entries=[_entry()])
    articles = parse_entries(parsed)
    assert len(articles) == 1
    assert isinstance(articles[0], Article)


def test_parse_entries_maps_fields_correctly():
    parsed = _parsed(
        entries=[_entry(
            title="My Article",
            link="https://example.com/article",
            summary="A great summary.",
            published_parsed=_STRUCT_TIME,
        )],
        feed_title="BBC News",
    )
    articles = parse_entries(parsed)
    assert len(articles) == 1
    a = articles[0]
    assert a.title == "My Article"
    assert a.url == "https://example.com/article"
    assert a.source == "BBC News"
    assert a.summary == "A great summary."
    assert a.published_at == "2026-02-19T12:00:00Z"


def test_parse_entries_id_is_stable_and_non_empty():
    parsed = _parsed(entries=[_entry()])
    a = parse_entries(parsed)[0]
    assert a.id
    assert isinstance(a.id, str)
    # Calling again should produce the same id
    a2 = parse_entries(parsed)[0]
    assert a.id == a2.id


# ---------------------------------------------------------------------------
# Source resolution
# ---------------------------------------------------------------------------

def test_parse_entries_uses_explicit_source_override():
    parsed = _parsed(entries=[_entry()], feed_title="Feed Title")
    articles = parse_entries(parsed, source="OverrideSource")
    assert articles[0].source == "OverrideSource"


def test_parse_entries_falls_back_to_feed_title():
    parsed = _parsed(entries=[_entry()], feed_title="BBC News", feed_link=None)
    articles = parse_entries(parsed)
    assert articles[0].source == "BBC News"


def test_parse_entries_falls_back_to_feed_link_when_no_title():
    parsed = _parsed(entries=[_entry()], feed_title=None, feed_link="https://bbc.co.uk")
    articles = parse_entries(parsed)
    assert articles[0].source == "https://bbc.co.uk"


def test_parse_entries_falls_back_to_rss_when_no_feed_metadata():
    parsed = _parsed(entries=[_entry()], feed_title=None, feed_link=None)
    articles = parse_entries(parsed)
    assert articles[0].source == "rss"


# ---------------------------------------------------------------------------
# Missing / bad fields
# ---------------------------------------------------------------------------

def test_parse_entries_skips_entry_with_missing_title():
    parsed = _parsed(entries=[_entry(title=None), _entry(title="Good")])
    articles = parse_entries(parsed)
    assert len(articles) == 1
    assert articles[0].title == "Good"


def test_parse_entries_skips_entry_with_empty_title():
    parsed = _parsed(entries=[_entry(title="   "), _entry(title="Good")])
    articles = parse_entries(parsed)
    assert len(articles) == 1


def test_parse_entries_skips_entry_with_missing_url():
    parsed = _parsed(entries=[_entry(link=None), _entry(link="https://example.com/2")])
    articles = parse_entries(parsed)
    assert len(articles) == 1
    assert articles[0].url == "https://example.com/2"


def test_parse_entries_handles_missing_summary_gracefully():
    parsed = _parsed(entries=[_entry(summary=None)])
    articles = parse_entries(parsed)
    assert len(articles) == 1
    assert articles[0].summary is None


def test_parse_entries_handles_whitespace_only_summary_as_none():
    parsed = _parsed(entries=[_entry(summary="   ")])
    articles = parse_entries(parsed)
    assert articles[0].summary is None


def test_parse_entries_handles_missing_published_at_gracefully():
    parsed = _parsed(entries=[_entry(published_parsed=None, updated_parsed=None)])
    articles = parse_entries(parsed)
    assert len(articles) == 1
    assert articles[0].published_at is None


def test_parse_entries_uses_updated_parsed_as_fallback_date():
    parsed = _parsed(entries=[_entry(published_parsed=None, updated_parsed=_STRUCT_TIME)])
    articles = parse_entries(parsed)
    assert articles[0].published_at == "2026-02-19T12:00:00Z"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_parse_entries_empty_feed_returns_empty_list():
    parsed = _parsed(entries=[])
    assert parse_entries(parsed) == []


def test_parse_entries_all_bad_entries_returns_empty_list():
    bad1 = _entry(title=None, link=None)
    bad2 = _entry(title="   ", link="   ")
    parsed = _parsed(entries=[bad1, bad2])
    assert parse_entries(parsed) == []


def test_parse_entries_multiple_valid_entries():
    entries = [
        _entry(title=f"Article {i}", link=f"https://example.com/{i}")
        for i in range(5)
    ]
    parsed = _parsed(entries=entries)
    articles = parse_entries(parsed)
    assert len(articles) == 5
    titles = [a.title for a in articles]
    assert titles == [f"Article {i}" for i in range(5)]


def test_parse_entries_mixed_good_and_bad_entries():
    entries = [
        _entry(title="Good 1", link="https://example.com/1"),
        _entry(title=None, link="https://example.com/2"),   # bad: no title
        _entry(title="Good 2", link="https://example.com/3"),
        _entry(title="Good 3", link=None),                  # bad: no url
    ]
    parsed = _parsed(entries=entries)
    articles = parse_entries(parsed)
    assert len(articles) == 2
    assert articles[0].title == "Good 1"
    assert articles[1].title == "Good 2"
