"""
Unit tests for rss_adapter.fetch_feed.

Covers:
- Happy path (200 OK with valid XML)
- Non-200 status codes raise AdapterError
- Empty / whitespace-only response body raises AdapterError
- Retry on transient network errors (Timeout, ConnectionError)
- Exhausts all retries and raises AdapterError
- Non-retryable exceptions propagate as AdapterError
- URL validation (empty string, whitespace-only, non-string)
- Trailing whitespace in URL is stripped
- Timeout parameter is forwarded to requests.get
"""
import pytest
import requests

from istina.model.adapters.rss_adapter import fetch_feed
from istina.model.adapters.adapter_error import AdapterError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class DummyResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


def make_fake_get(response: DummyResponse):
    """Returns a fake requests.get that always returns a fixed response."""
    def fake_get(url, timeout):
        return response
    return fake_get


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_fetch_feed_returns_xml_on_200(monkeypatch):
    monkeypatch.setattr(requests, "get", make_fake_get(DummyResponse(200, "<rss>ok</rss>")))
    xml = fetch_feed("https://example.com/rss.xml")
    assert xml.strip() == "<rss>ok</rss>"


def test_fetch_feed_strips_url_whitespace(monkeypatch):
    """Leading/trailing whitespace in URL should be stripped before use."""
    captured = {}

    def fake_get(url, timeout):
        captured["url"] = url
        return DummyResponse(200, "<rss/>")

    monkeypatch.setattr(requests, "get", fake_get)
    fetch_feed("  https://example.com/rss.xml  ")
    assert captured["url"] == "https://example.com/rss.xml"


def test_fetch_feed_forwards_timeout(monkeypatch):
    """Custom timeout value must be passed to requests.get."""
    captured = {}

    def fake_get(url, timeout):
        captured["timeout"] = timeout
        return DummyResponse(200, "<rss/>")

    monkeypatch.setattr(requests, "get", fake_get)
    fetch_feed("https://example.com/rss.xml", timeout=42)
    assert captured["timeout"] == 42


# ---------------------------------------------------------------------------
# HTTP error codes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status_code", [400, 403, 404, 500, 503])
def test_fetch_feed_non_200_raises_adapter_error(monkeypatch, status_code):
    monkeypatch.setattr(requests, "get", make_fake_get(DummyResponse(status_code, "error")))
    with pytest.raises(AdapterError) as exc:
        fetch_feed("https://example.com/rss.xml")
    assert str(status_code) in str(exc.value)


# ---------------------------------------------------------------------------
# Empty / whitespace body
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body", ["", "   ", "\n\t"])
def test_fetch_feed_empty_body_raises_adapter_error(monkeypatch, body):
    monkeypatch.setattr(requests, "get", make_fake_get(DummyResponse(200, body)))
    with pytest.raises(AdapterError) as exc:
        fetch_feed("https://example.com/rss.xml")
    assert "empty" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# Retry behaviour
# ---------------------------------------------------------------------------

def test_fetch_feed_retries_on_timeout_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, timeout):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise requests.exceptions.Timeout("timeout")
        return DummyResponse(200, "<rss>ok</rss>")

    monkeypatch.setattr(requests, "get", fake_get)
    xml = fetch_feed("https://example.com/rss.xml")
    assert xml.strip() == "<rss>ok</rss>"
    assert calls["n"] == 3  # failed twice, succeeded on 3rd


def test_fetch_feed_retries_on_connection_error_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.exceptions.ConnectionError("connection refused")
        return DummyResponse(200, "<rss>ok</rss>")

    monkeypatch.setattr(requests, "get", fake_get)
    xml = fetch_feed("https://example.com/rss.xml")
    assert xml.strip() == "<rss>ok</rss>"
    assert calls["n"] == 2


def test_fetch_feed_exhausts_retries_on_timeout_raises_adapter_error(monkeypatch):
    def fake_get(url, timeout):
        raise requests.exceptions.Timeout("always times out")

    monkeypatch.setattr(requests, "get", fake_get)
    with pytest.raises(AdapterError):
        fetch_feed("https://example.com/rss.xml")


def test_fetch_feed_exhausts_retries_on_non_200_raises_adapter_error(monkeypatch):
    """A persistent non-200 response should raise AdapterError after all retries."""
    monkeypatch.setattr(requests, "get", make_fake_get(DummyResponse(503, "down")))
    with pytest.raises(AdapterError) as exc:
        fetch_feed("https://example.com/rss.xml")
    assert "503" in str(exc.value)


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_url", ["", "   ", "\t\n"])
def test_fetch_feed_empty_url_raises_value_error(bad_url):
    with pytest.raises(ValueError):
        fetch_feed(bad_url)


@pytest.mark.parametrize("bad_url", [None, 123, [], {}])
def test_fetch_feed_non_string_url_raises_value_error(bad_url):
    with pytest.raises(ValueError):
        fetch_feed(bad_url)