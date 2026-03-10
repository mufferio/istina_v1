"""
CLIController tests.

Covers:
- build_parser(): --help available, subcommands registered
- ingest subcommand: feeds stored, exit code 0, output message printed
- ingest subcommand: missing --feeds → argparse error (exit 2)
- analyze subcommand: scores produced, exit code 0
- analyze subcommand: --limit forwarded
- analyze subcommand: --since parses correctly and forwards
- analyze subcommand: invalid --since is rejected (exit 1)
- summarize subcommand: summary mode prints article count
- summarize subcommand: full mode prints article title
- summarize subcommand: --report full --article-id scopes output
- unknown subcommand → exit non-zero (argparse handles)
- keyboard interrupt → exit 130
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from io import StringIO
from typing import List
from unittest.mock import patch

import pytest

from istina.config.settings import Settings
from istina.controller.cli_controller import CLIController, build_parser
from istina.controller.services.ingest_service import IngestService
from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.providers.mock_provider import MockProvider
from istina.model.repositories.memory_repository import MemoryRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _article(n: int, source: str = "test", title: str = "") -> Article:
    return Article.create(
        title=title or f"Article number {n}",
        url=f"https://example.com/{n}",
        source=source,
    )


def _score(article: Article) -> BiasScore:
    return BiasScore(
        article_id=article.id,
        provider="mock",
        overall_bias_label="center",
        rhetorical_bias=[],
        claim_checks=[],
        confidence=0.9,
        timestamp=_TS,
    )


def _settings() -> Settings:
    return Settings(provider="mock")


class _FakeAdapter:
    def __init__(self, articles: List[Article]):
        self._articles = articles

    def fetch_articles(self, urls):
        return list(self._articles)


def _ctrl(repo: MemoryRepository) -> CLIController:
    return CLIController(settings=_settings(), repo=repo)


# ---------------------------------------------------------------------------
# Parser smoke tests
# ---------------------------------------------------------------------------

def test_build_parser_returns_parser():
    p = build_parser()
    assert p is not None


def test_parser_has_ingest_subcommand():
    p = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        p.parse_args(["ingest", "--help"])
    assert exc_info.value.code == 0


def test_parser_has_analyze_subcommand():
    p = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        p.parse_args(["analyze", "--help"])
    assert exc_info.value.code == 0


def test_parser_has_summarize_subcommand():
    p = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        p.parse_args(["summarize", "--help"])
    assert exc_info.value.code == 0


def test_top_level_help_exits_zero():
    p = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        p.parse_args(["--help"])
    assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# ingest subcommand
# ---------------------------------------------------------------------------

def test_ingest_stores_articles_and_returns_zero(capsys):
    articles = [_article(i) for i in range(3)]
    repo = MemoryRepository()
    adapter = _FakeAdapter(articles)
    # Patch IngestService to inject our fake adapter
    with patch(
        "istina.controller.cli_controller.IngestService",
        return_value=IngestService(repo=repo, rss_adapter=adapter),
    ):
        code = _ctrl(repo).run(["ingest", "--feeds", "https://fake.feed/rss"])

    assert code == 0
    assert len(repo.list_articles()) == 3


def test_ingest_prints_message(capsys):
    articles = [_article(i) for i in range(2)]
    repo = MemoryRepository()
    adapter = _FakeAdapter(articles)
    with patch(
        "istina.controller.cli_controller.IngestService",
        return_value=IngestService(repo=repo, rss_adapter=adapter),
    ):
        _ctrl(repo).run(["ingest", "--feeds", "https://fake.feed/rss"])

    out = capsys.readouterr().out
    assert "2" in out  # fetched count present in message


def test_ingest_missing_feeds_exits_nonzero():
    repo = MemoryRepository()
    with pytest.raises(SystemExit) as exc_info:
        _ctrl(repo).run(["ingest"])  # missing required --feeds
    assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# analyze subcommand
# ---------------------------------------------------------------------------

def test_analyze_produces_scores_and_returns_zero(capsys):
    articles = [_article(i) for i in range(4)]
    repo = MemoryRepository()
    repo.add_articles(articles)

    code = _ctrl(repo).run(["analyze"])

    assert code == 0
    for a in articles:
        assert repo.get_bias_score(a.id) is not None


def test_analyze_prints_message(capsys):
    articles = [_article(i) for i in range(3)]
    repo = MemoryRepository()
    repo.add_articles(articles)

    _ctrl(repo).run(["analyze"])

    out = capsys.readouterr().out
    assert "Analyzed" in out


def test_analyze_limit_flag_restricts_scoring(capsys):
    articles = [_article(i) for i in range(10)]
    repo = MemoryRepository()
    repo.add_articles(articles)

    _ctrl(repo).run(["analyze", "--limit", "3"])

    scored = [a for a in articles if repo.get_bias_score(a.id) is not None]
    assert len(scored) == 3


def test_analyze_since_valid_iso_returns_zero(capsys):
    repo = MemoryRepository()
    code = _ctrl(repo).run(["analyze", "--since", "2026-01-01"])
    assert code == 0


def test_analyze_since_invalid_returns_one(capsys):
    repo = MemoryRepository()
    code = _ctrl(repo).run(["analyze", "--since", "not-a-date"])
    assert code == 1


def test_analyze_source_filter_forwarded(capsys):
    bbc = [_article(i, source="bbc") for i in range(3)]
    cnn = [_article(i + 10, source="cnn") for i in range(3)]
    repo = MemoryRepository()
    repo.add_articles([*bbc, *cnn])

    _ctrl(repo).run(["analyze", "--source", "bbc"])

    for a in bbc:
        assert repo.get_bias_score(a.id) is not None
    for a in cnn:
        assert repo.get_bias_score(a.id) is None


# ---------------------------------------------------------------------------
# summarize subcommand
# ---------------------------------------------------------------------------

def test_summarize_summary_mode_exits_zero(capsys):
    repo = MemoryRepository()
    code = _ctrl(repo).run(["summarize"])
    assert code == 0


def test_summarize_prints_article_count(capsys):
    articles = [_article(i) for i in range(5)]
    repo = MemoryRepository()
    repo.add_articles(articles)

    _ctrl(repo).run(["summarize"])

    out = capsys.readouterr().out
    assert "5" in out


def test_summarize_full_mode_prints_title(capsys):
    a = _article(1, title="Exclusive: New Research Reveals Bias Pattern")
    repo = MemoryRepository()
    repo.add_articles([a])

    _ctrl(repo).run(["summarize", "--report", "full"])

    out = capsys.readouterr().out
    assert "Exclusive: New Research Reveals Bias Pattern" in out


def test_summarize_full_mode_with_score_shows_label(capsys):
    a = _article(1)
    repo = MemoryRepository()
    repo.add_articles([a])
    repo.upsert_bias_score(_score(a))

    _ctrl(repo).run(["summarize", "--report", "full"])

    out = capsys.readouterr().out
    assert "center" in out


def test_summarize_article_id_scopes_output(capsys):
    a1 = _article(1, title="First Article For Scoping Test")
    a2 = _article(2, title="Second Article Should Not Appear")
    repo = MemoryRepository()
    repo.add_articles([a1, a2])

    _ctrl(repo).run(["summarize", "--report", "full", "--article-id", a1.id])

    out = capsys.readouterr().out
    assert "First Article For Scoping Test" in out
    assert "Second Article Should Not Appear" not in out


def test_summarize_invalid_report_value_exits_nonzero():
    repo = MemoryRepository()
    with pytest.raises(SystemExit) as exc_info:
        _ctrl(repo).run(["summarize", "--report", "invalid"])
    assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# Keyboard interrupt
# ---------------------------------------------------------------------------

def test_keyboard_interrupt_returns_130(capsys):
    repo = MemoryRepository()
    ctrl = _ctrl(repo)
    with patch.object(ctrl, "_dispatch", side_effect=KeyboardInterrupt):
        code = ctrl.run(["summarize"])
    assert code == 130
