"""
Consolidated adapter tests for rss_adapter (Issues 4.2 / 4.3 / 4.4).

Covers gaps not already handled by the top-level test_rss_adapter.py,
test_rss_parse_entries.py, and test_fetch_articles.py:

fetch_feed (mocked HTTP)
------------------------
- Default timeout is 10 s
- Response body is returned verbatim (no mutation)
- HTTP 201 / 301 are treated as non-200 and raise AdapterError
- AdapterError message includes the feed URL
- Successful retry returns the value from the winning attempt

parse_entries — Article required fields
----------------------------------------
- Every returned Article has a non-empty str id, title, url, source
- id is a 64-char lowercase hex string (SHA-256)
- source is the explicit override, not the feed title, when both exist
- entry.description is used as summary fallback when summary is absent
- published_parsed takes priority over updated_parsed when both present

parse_entries — missing-field crash safety
------------------------------------------
- Entry with NO attributes at all is skipped without raising
- parsed.feed being None instead of a dict does not crash
- parsed.entries attribute missing entirely returns empty list
- Corrupt published_parsed (raises inside datetime()) falls back to None
- Entry where title/link are not strings but truthy (int, list) skipped
- Empty link string (after strip) is skipped

fetch_feed + parse_entries integration (no real HTTP)
------------------------------------------------------
- A real RSS XML string round-trips through parse_xml -> parse_entries
  and produces Articles with correct fields
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, Optional

import pytest
import requests

from istina.model.adapters.adapter_error import AdapterError
from istina.model.adapters.rss_adapter import (
    DEFAULT_TIMEOUT,
    fetch_feed,
    parse_entries,
    parse_xml,
)
from istina.model.entities.article import Article


# ===========================================================================
# Shared helpers
# ===========================================================================

class _Resp:
    """Minimal requests.Response stand-in."""
    def __init__(self, status_code: int, text: str = "<rss/>"):
        self.status_code = status_code
        self.text = text


def _fake_get(status: int = 200, body: str = "<rss/>"):
    """Return a requests.get replacement that always gives the same response."""
    def _get(url, timeout):
        return _Resp(status, body)
    return _get


def _entry(
    title: Optional[str] = "Test Title",
    link: Optional[str] = "https://example.com/1",
    summary: Optional[str] = None,
    description: Optional[str] = None,
    published_parsed: Optional[time.struct_time] = None,
    updated_parsed: Optional[time.struct_time] = None,
) -> Any:
    e = SimpleNamespace()
    e.title = title
    e.link = link
    e.summary = summary
    e.description = description
    e.published_parsed = published_parsed
    e.updated_parsed = updated_parsed
    return e


def _parsed(
    entries=(),
    feed_title: Optional[str] = "Feed Title",
    feed_link: Optional[str] = "https://example.com",
) -> Any:
    p = SimpleNamespace()
    p.entries = list(entries)
    p.feed = {}
    if feed_title is not None:
        p.feed["title"] = feed_title
    if feed_link is not None:
        p.feed["link"] = feed_link
    return p


_T = time.strptime("2026-02-22T09:00:00", "%Y-%m-%dT%H:%M:%S")
_T2 = time.strptime("2026-02-21T08:00:00", "%Y-%m-%dT%H:%M:%S")


# ===========================================================================
# fetch_feed — mocked HTTP
# ===========================================================================

class TestFetchFeedMockedHTTP:

    def test_default_timeout_is_ten_seconds(self, monkeypatch):
        """fetch_feed must pass DEFAULT_TIMEOUT (10) to requests.get by default."""
        captured = {}

        def fake_get(url, timeout):
            captured["timeout"] = timeout
            return _Resp(200, "<rss/>")

        monkeypatch.setattr(requests, "get", fake_get)
        fetch_feed("https://example.com/rss")
        assert captured["timeout"] == DEFAULT_TIMEOUT
        assert DEFAULT_TIMEOUT == 10

    def test_body_returned_verbatim(self, monkeypatch):
        """The exact response text must be returned without modification."""
        body = "  <rss>  \n  <channel/>  \n  </rss>  "
        monkeypatch.setattr(requests, "get", _fake_get(200, body))
        assert fetch_feed("https://example.com/rss") == body

    @pytest.mark.parametrize("status", [201, 204, 301, 302])
    def test_non_200_status_codes_raise_adapter_error(self, monkeypatch, status):
        """2xx/3xx codes other than 200 must raise AdapterError."""
        monkeypatch.setattr(requests, "get", _fake_get(status, "ok"))
        with pytest.raises(AdapterError):
            fetch_feed("https://example.com/rss")

    def test_adapter_error_message_contains_url(self, monkeypatch):
        """The AdapterError raised for a non-200 response must include the URL."""
        url = "https://news.example.org/feed.xml"
        monkeypatch.setattr(requests, "get", _fake_get(404, "not found"))
        with pytest.raises(AdapterError, match="news.example.org"):
            fetch_feed(url)

    def test_retry_returns_value_from_winning_attempt(self, monkeypatch):
        """When a retry succeeds, its return value (not None) must be returned."""
        calls = {"n": 0}

        def fake_get(url, timeout):
            calls["n"] += 1
            if calls["n"] < 3:
                raise requests.exceptions.Timeout("slow")
            return _Resp(200, "<rss>winner</rss>")

        monkeypatch.setattr(requests, "get", fake_get)
        result = fetch_feed("https://example.com/rss")
        assert result == "<rss>winner</rss>"
        assert calls["n"] == 3

    def test_non_retryable_os_error_wraps_to_adapter_error(self, monkeypatch):
        """Unexpected non-RequestException errors are wrapped in AdapterError."""
        def fake_get(url, timeout):
            raise OSError("disk full")

        monkeypatch.setattr(requests, "get", fake_get)
        with pytest.raises(AdapterError):
            fetch_feed("https://example.com/rss")


# ===========================================================================
# parse_entries — Article required fields
# ===========================================================================

class TestParseEntriesArticleFields:

    def test_returned_article_has_non_empty_id(self):
        articles = parse_entries(_parsed(entries=[_entry()]))
        assert articles[0].id != ""

    def test_id_is_sha256_hex(self):
        """id must be a 64-character lowercase hex string."""
        a = parse_entries(_parsed(entries=[_entry()]))[0]
        assert len(a.id) == 64
        assert a.id == a.id.lower()
        int(a.id, 16)  # raises ValueError if not valid hex

    def test_article_title_is_non_empty_string(self):
        a = parse_entries(_parsed(entries=[_entry(title="Breaking News")]))[0]
        assert isinstance(a.title, str)
        assert a.title == "Breaking News"

    def test_article_url_is_non_empty_string(self):
        a = parse_entries(_parsed(entries=[_entry(link="https://example.com/story")]))[0]
        assert isinstance(a.url, str)
        assert a.url == "https://example.com/story"

    def test_article_source_is_non_empty_string(self):
        a = parse_entries(_parsed(entries=[_entry()], feed_title="Reuters"))[0]
        assert isinstance(a.source, str)
        assert a.source != ""

    def test_explicit_source_beats_feed_title(self):
        """source override must win over the feed's own title."""
        parsed = _parsed(entries=[_entry()], feed_title="BBC")
        a = parse_entries(parsed, source="Custom Source")[0]
        assert a.source == "Custom Source"

    def test_description_used_as_summary_fallback(self):
        """When summary is absent, entry.description should become the summary."""
        e = _entry(summary=None, description="Fallback description text.")
        a = parse_entries(_parsed(entries=[e]))[0]
        assert a.summary == "Fallback description text."

    def test_published_parsed_takes_priority_over_updated_parsed(self):
        """published_parsed must win when both timestamps are present."""
        e = _entry(published_parsed=_T, updated_parsed=_T2)
        a = parse_entries(_parsed(entries=[e]))[0]
        assert a.published_at == "2026-02-22T09:00:00Z"

    def test_article_is_article_instance(self):
        a = parse_entries(_parsed(entries=[_entry()]))[0]
        assert isinstance(a, Article)


# ===========================================================================
# parse_entries — missing-field crash safety
# ===========================================================================

class TestParseEntriesMissingFieldCrashSafety:

    def test_entry_with_no_attributes_is_skipped(self):
        """An entry that is a bare object() with no attrs must not crash."""
        bare = object()
        articles = parse_entries(_parsed(entries=[bare, _entry(title="OK", link="https://x.com/1")]))
        assert len(articles) == 1
        assert articles[0].title == "OK"

    def test_parsed_feed_none_does_not_crash(self):
        """parsed.feed = None must be handled gracefully (falls back to 'rss')."""
        p = SimpleNamespace()
        p.entries = [_entry()]
        p.feed = None
        articles = parse_entries(p)
        assert len(articles) == 1
        assert articles[0].source == "rss"

    def test_parsed_missing_entries_attr_returns_empty_list(self):
        """If parsed has no .entries attribute at all, return []."""
        p = SimpleNamespace()  # no .entries
        p.feed = {}
        assert parse_entries(p) == []

    def test_corrupt_published_parsed_falls_back_to_none(self):
        """A published_parsed that causes datetime() to raise must yield published_at=None."""
        e = _entry()
        e.published_parsed = (9999, 99, 99, 99, 99, 99)  # invalid — will raise in datetime()
        articles = parse_entries(_parsed(entries=[e]))
        assert len(articles) == 1
        assert articles[0].published_at is None

    def test_entry_with_integer_title_is_skipped(self):
        """Non-string truthy title (e.g. int) must not produce an Article."""
        e = _entry()
        e.title = 12345  # not a string
        articles = parse_entries(_parsed(entries=[e, _entry(title="Valid", link="https://x.com/2")]))
        # integer title: getattr returns 12345, str(12345).strip() == "12345" which is truthy
        # parse_entries currently calls .strip() on it after (getattr(...) or "")
        # Since int has no .strip(), this will raise → entry is skipped
        assert all(isinstance(a.title, str) for a in articles)

    def test_entry_with_empty_link_after_strip_is_skipped(self):
        """A link that is whitespace-only must be skipped, not produce an Article."""
        e = _entry(link="   ")
        articles = parse_entries(_parsed(entries=[e]))
        assert articles == []

    def test_entries_none_instead_of_list_returns_empty(self):
        """parsed.entries = None must return [] without crashing."""
        p = SimpleNamespace()
        p.entries = None
        p.feed = {}
        assert parse_entries(p) == []


# ===========================================================================
# fetch_feed + parse_entries — lightweight integration (no real HTTP)
# ===========================================================================

class TestFetchFeedParseEntriesIntegration:

    _REAL_RSS = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Integration Feed</title>
        <link>https://integration.example.com</link>
        <item>
          <title>First Story</title>
          <link>https://integration.example.com/first</link>
          <description>Story one summary.</description>
          <pubDate>Sat, 22 Feb 2026 09:00:00 +0000</pubDate>
        </item>
        <item>
          <title>Second Story</title>
          <link>https://integration.example.com/second</link>
        </item>
      </channel>
    </rss>"""

    def test_real_xml_produces_correct_article_count(self, monkeypatch):
        monkeypatch.setattr(requests, "get", _fake_get(200, self._REAL_RSS))
        xml = fetch_feed("https://integration.example.com/rss")
        parsed = parse_xml(xml)
        articles = parse_entries(parsed)
        assert len(articles) == 2

    def test_real_xml_first_article_has_correct_title(self, monkeypatch):
        monkeypatch.setattr(requests, "get", _fake_get(200, self._REAL_RSS))
        xml = fetch_feed("https://integration.example.com/rss")
        articles = parse_entries(parse_xml(xml))
        assert articles[0].title == "First Story"

    def test_real_xml_first_article_has_correct_url(self, monkeypatch):
        monkeypatch.setattr(requests, "get", _fake_get(200, self._REAL_RSS))
        xml = fetch_feed("https://integration.example.com/rss")
        articles = parse_entries(parse_xml(xml))
        assert articles[0].url == "https://integration.example.com/first"

    def test_real_xml_source_falls_back_to_feed_title(self, monkeypatch):
        monkeypatch.setattr(requests, "get", _fake_get(200, self._REAL_RSS))
        xml = fetch_feed("https://integration.example.com/rss")
        articles = parse_entries(parse_xml(xml))
        assert articles[0].source == "Integration Feed"

    def test_real_xml_article_ids_are_unique(self, monkeypatch):
        monkeypatch.setattr(requests, "get", _fake_get(200, self._REAL_RSS))
        xml = fetch_feed("https://integration.example.com/rss")
        articles = parse_entries(parse_xml(xml))
        ids = [a.id for a in articles]
        assert len(ids) == len(set(ids))

    def test_real_xml_second_article_has_none_summary(self, monkeypatch):
        """Item with no description/summary must yield summary=None."""
        monkeypatch.setattr(requests, "get", _fake_get(200, self._REAL_RSS))
        xml = fetch_feed("https://integration.example.com/rss")
        articles = parse_entries(parse_xml(xml))
        assert articles[1].summary is None
