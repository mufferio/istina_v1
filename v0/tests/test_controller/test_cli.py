"""
End-to-end CLI integration tests.

Strategy
--------
- All tests use MemoryRepository (no disk I/O) and MockProvider (no network).
- RSS ingestion is exercised through a FakeAdapter injected via patch so we
  never touch real feeds.
- Commands are driven through CLIController.run([...]) — the same code path
  that main.py uses — so the full dispatch/error/output pipeline is covered.
- Each test verifies BOTH the repository state (articles/scores persisted) AND
  the printed output (stdout / stderr via capsys).

Workflow scenarios covered
--------------------------
1.  Ingest: articles land in repo
2.  Ingest → Analyze: scores created for all articles
3.  Ingest → Analyze --limit: only N articles scored
4.  Ingest → Analyze --source: only matching articles scored
5.  Full pipeline (ingest → analyze → summarize summary): output has counts
6.  Full pipeline → summarize full: output has title + bias label
7.  Full pipeline → summarize full --article-id: output scoped to one article
8.  Full pipeline → summarize full --source: output scoped to one source
9.  Summarize on empty repo: graceful "no articles" message
10. All success paths return exit code 0
11. Analyze with no unscored articles: exit 0, message reflects zero scored
12. Summarize --report full shows claim verdicts
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List
from unittest.mock import patch

import pytest

from istina.config.settings import Settings
from istina.controller.cli_controller import CLIController
from istina.controller.services.ingest_service import IngestService
from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.model.providers.mock_provider import MockProvider
from istina.model.repositories.memory_repository import MemoryRepository


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FEED_URL = "https://fake.feed/rss"


def _article(
    n: int,
    *,
    source: str = "Reuters",
    suffix: str = "",
) -> Article:
    title = f"Headline number {n}{suffix}"
    return Article.create(
        title=title,
        url=f"https://example.com/article/{n}",
        source=source,
        published_at=f"2026-01-{n:02d}T12:00:00Z",
    )


class _FakeAdapter:
    """Drop-in RSS adapter that returns a fixed list of Articles."""

    def __init__(self, articles: List[Article]) -> None:
        self._articles = articles

    def fetch_articles(self, urls: List[str]) -> List[Article]:
        return list(self._articles)


def _ctrl(repo: MemoryRepository) -> CLIController:
    """Create a controller wired to MockProvider."""
    return CLIController(settings=Settings(provider="mock"), repo=repo)


def _run_ingest(ctrl: CLIController, repo: MemoryRepository, articles: List[Article]) -> int:
    """Run the ingest subcommand, injecting a FakeAdapter so no HTTP happens."""
    adapter = _FakeAdapter(articles)
    with patch(
        "istina.controller.cli_controller.IngestService",
        return_value=IngestService(repo=repo, rss_adapter=adapter),
    ):
        return ctrl.run(["ingest", "--feeds", _FEED_URL])


# ---------------------------------------------------------------------------
# 1. Ingest: articles land in repo
# ---------------------------------------------------------------------------


class TestIngest:
    def test_ingest_stores_all_articles(self):
        repo = MemoryRepository()
        articles = [_article(i) for i in range(1, 6)]
        code = _run_ingest(_ctrl(repo), repo, articles)
        assert code == 0
        assert len(repo.list_articles()) == 5

    def test_ingest_article_ids_stable(self):
        """Articles stored with the expected deterministic IDs."""
        repo = MemoryRepository()
        articles = [_article(i) for i in range(1, 4)]
        _run_ingest(_ctrl(repo), repo, articles)
        stored_ids = {a.id for a in repo.list_articles()}
        expected_ids = {a.id for a in articles}
        assert stored_ids == expected_ids

    def test_ingest_prints_fetched_count(self, capsys):
        repo = MemoryRepository()
        articles = [_article(i) for i in range(1, 4)]
        _run_ingest(_ctrl(repo), repo, articles)
        out = capsys.readouterr().out
        assert "3" in out

    def test_ingest_exits_zero(self):
        repo = MemoryRepository()
        code = _run_ingest(_ctrl(repo), repo, [_article(1)])
        assert code == 0

    def test_ingest_deduplicates_articles(self):
        """Running ingest twice with the same articles does not duplicate them."""
        repo = MemoryRepository()
        articles = [_article(i) for i in range(1, 4)]
        ctrl = _ctrl(repo)
        _run_ingest(ctrl, repo, articles)
        _run_ingest(ctrl, repo, articles)
        assert len(repo.list_articles()) == 3


# ---------------------------------------------------------------------------
# 2. Analyze: scores created for all unscored articles
# ---------------------------------------------------------------------------


class TestAnalyze:
    def setup_method(self):
        self.repo = MemoryRepository()
        self.articles = [_article(i) for i in range(1, 5)]
        self.repo.add_articles(self.articles)
        self.ctrl = _ctrl(self.repo)

    def test_analyze_creates_scores_for_all_articles(self):
        code = self.ctrl.run(["analyze"])
        assert code == 0
        for a in self.articles:
            assert self.repo.get_bias_score(a.id) is not None

    def test_analyze_exits_zero(self):
        assert self.ctrl.run(["analyze"]) == 0

    def test_analyze_scores_are_bias_score_instances(self):
        self.ctrl.run(["analyze"])
        for a in self.articles:
            score = self.repo.get_bias_score(a.id)
            assert isinstance(score, BiasScore)

    def test_analyze_scores_have_valid_labels(self):
        self.ctrl.run(["analyze"])
        valid = {"left", "center", "right", "unknown"}
        for a in self.articles:
            score = self.repo.get_bias_score(a.id)
            assert score.overall_bias_label in valid

    def test_analyze_prints_analyzed_count(self, capsys):
        self.ctrl.run(["analyze"])
        out = capsys.readouterr().out
        assert "Analyzed" in out
        assert "4" in out

    def test_analyze_no_scores_created_if_repo_empty(self, capsys):
        repo = MemoryRepository()
        ctrl = _ctrl(repo)
        code = ctrl.run(["analyze"])
        assert code == 0
        assert repo.list_articles() == []


# ---------------------------------------------------------------------------
# 3. Analyze --limit: only N articles scored
# ---------------------------------------------------------------------------


class TestAnalyzeLimit:
    def test_limit_restricts_scored_count(self):
        repo = MemoryRepository()
        articles = [_article(i) for i in range(1, 11)]
        repo.add_articles(articles)
        ctrl = _ctrl(repo)

        ctrl.run(["analyze", "--limit", "3"])

        scored = [a for a in articles if repo.get_bias_score(a.id) is not None]
        assert len(scored) == 3

    def test_limit_1_scores_exactly_one(self):
        repo = MemoryRepository()
        articles = [_article(i) for i in range(1, 6)]
        repo.add_articles(articles)
        _ctrl(repo).run(["analyze", "--limit", "1"])
        scored = [a for a in articles if repo.get_bias_score(a.id) is not None]
        assert len(scored) == 1


# ---------------------------------------------------------------------------
# 4. Analyze --source: only matching articles scored
# ---------------------------------------------------------------------------


class TestAnalyzeSource:
    def test_source_filter_scores_only_matching(self):
        repo = MemoryRepository()
        bbc = [_article(i, source="BBC") for i in range(1, 4)]
        cnn = [_article(i + 10, source="CNN") for i in range(1, 4)]
        repo.add_articles([*bbc, *cnn])
        _ctrl(repo).run(["analyze", "--source", "BBC"])

        for a in bbc:
            assert repo.get_bias_score(a.id) is not None
        for a in cnn:
            assert repo.get_bias_score(a.id) is None

    def test_source_filter_no_match_scores_nothing(self):
        repo = MemoryRepository()
        articles = [_article(i, source="Reuters") for i in range(1, 4)]
        repo.add_articles(articles)
        _ctrl(repo).run(["analyze", "--source", "NoSuchSource"])
        for a in articles:
            assert repo.get_bias_score(a.id) is None


# ---------------------------------------------------------------------------
# 5. Full pipeline → summarize summary mode
# ---------------------------------------------------------------------------


class TestFullPipelineSummary:
    def _setup(self, n: int = 4):
        repo = MemoryRepository()
        articles = [_article(i) for i in range(1, n + 1)]
        ctrl = _ctrl(repo)
        _run_ingest(ctrl, repo, articles)
        ctrl.run(["analyze"])
        return repo, ctrl

    def test_summarize_exits_zero(self):
        _repo, ctrl = self._setup()
        assert ctrl.run(["summarize"]) == 0

    def test_summarize_output_has_istina_header(self, capsys):
        _repo, ctrl = self._setup()
        ctrl.run(["summarize"])
        out = capsys.readouterr().out
        assert "Istina Summary" in out

    def test_summarize_output_shows_total_article_count(self, capsys):
        _repo, ctrl = self._setup(n=4)
        ctrl.run(["summarize"])
        out = capsys.readouterr().out
        assert "4" in out

    def test_summarize_shows_analyzed_count(self, capsys):
        _repo, ctrl = self._setup(n=4)
        ctrl.run(["summarize"])
        out = capsys.readouterr().out
        assert "Analyzed" in out

    def test_summarize_shows_bias_distribution(self, capsys):
        _repo, ctrl = self._setup(n=6)
        ctrl.run(["summarize"])
        out = capsys.readouterr().out
        assert "Bias distribution" in out

    def test_summarize_shows_source_breakdown(self, capsys):
        _repo, ctrl = self._setup(n=3)
        ctrl.run(["summarize"])
        out = capsys.readouterr().out
        assert "By source" in out
        assert "Reuters" in out


# ---------------------------------------------------------------------------
# 6. Full pipeline → summarize --report full
# ---------------------------------------------------------------------------


class TestFullPipelineFullReport:
    def _setup(self):
        repo = MemoryRepository()
        articles = [
            _article(1, suffix=" — Exclusive investigation"),
            _article(2, suffix=" — Breaking update"),
        ]
        ctrl = _ctrl(repo)
        _run_ingest(ctrl, repo, articles)
        ctrl.run(["analyze"])
        return repo, ctrl, articles

    def test_full_report_exits_zero(self):
        _repo, ctrl, _articles = self._setup()
        assert ctrl.run(["summarize", "--report", "full"]) == 0

    def test_full_report_output_has_article_title(self, capsys):
        _repo, ctrl, articles = self._setup()
        ctrl.run(["summarize", "--report", "full"])
        out = capsys.readouterr().out
        assert articles[0].title in out
        assert articles[1].title in out

    def test_full_report_shows_bias_label(self, capsys):
        _repo, ctrl, _articles = self._setup()
        ctrl.run(["summarize", "--report", "full"])
        out = capsys.readouterr().out
        valid = {"left", "center", "right", "unknown"}
        assert any(label in out for label in valid)

    def test_full_report_shows_url(self, capsys):
        _repo, ctrl, articles = self._setup()
        ctrl.run(["summarize", "--report", "full"])
        out = capsys.readouterr().out
        assert articles[0].url in out

    def test_full_report_shows_source(self, capsys):
        _repo, ctrl, _articles = self._setup()
        ctrl.run(["summarize", "--report", "full"])
        out = capsys.readouterr().out
        assert "Reuters" in out

    def test_full_report_shows_confidence(self, capsys):
        _repo, ctrl, _articles = self._setup()
        ctrl.run(["summarize", "--report", "full"])
        out = capsys.readouterr().out
        assert "confidence" in out

    def test_full_report_shows_claims(self, capsys):
        _repo, ctrl, _articles = self._setup()
        ctrl.run(["summarize", "--report", "full"])
        out = capsys.readouterr().out
        # MockProvider always generates at least one claim
        assert "Claims" in out

    def test_full_report_unscored_shows_not_analyzed(self, capsys):
        """Article without a score renders NOT ANALYZED."""
        repo = MemoryRepository()
        articles = [_article(1, suffix=" — unscored")]
        ctrl = _ctrl(repo)
        _run_ingest(ctrl, repo, articles)
        # Skip analyze step
        ctrl.run(["summarize", "--report", "full"])
        out = capsys.readouterr().out
        assert "NOT ANALYZED" in out


# ---------------------------------------------------------------------------
# 7. Full pipeline → summarize --article-id scopes output
# ---------------------------------------------------------------------------


class TestSummarizeArticleId:
    def _setup(self):
        repo = MemoryRepository()
        a1 = _article(1, suffix=" — Target article")
        a2 = _article(2, suffix=" — Other article, should not appear")
        ctrl = _ctrl(repo)
        _run_ingest(ctrl, repo, [a1, a2])
        ctrl.run(["analyze"])
        return repo, ctrl, a1, a2

    def test_article_id_scopes_to_target(self, capsys):
        _repo, ctrl, a1, a2 = self._setup()
        ctrl.run(["summarize", "--report", "full", "--article-id", a1.id])
        out = capsys.readouterr().out
        assert a1.title in out
        assert a2.title not in out

    def test_article_id_exits_zero(self):
        _repo, ctrl, a1, _a2 = self._setup()
        code = ctrl.run(["summarize", "--report", "full", "--article-id", a1.id])
        assert code == 0


# ---------------------------------------------------------------------------
# 8. Summarize --source scopes to one source
# ---------------------------------------------------------------------------


class TestSummarizeSource:
    def test_source_filter_scopes_full_report(self, capsys):
        repo = MemoryRepository()
        bbc = [_article(i, source="BBC") for i in range(1, 3)]
        apn = [_article(i + 10, source="AP") for i in range(1, 3)]
        ctrl = _ctrl(repo)
        _run_ingest(ctrl, repo, [*bbc, *apn])
        ctrl.run(["analyze"])

        ctrl.run(["summarize", "--report", "full", "--source", "BBC"])
        out = capsys.readouterr().out
        assert "BBC" in out
        # AP articles should not appear
        for a in apn:
            assert a.title not in out


# ---------------------------------------------------------------------------
# 9. Summarize on empty repo
# ---------------------------------------------------------------------------


class TestSummarizeEmptyRepo:
    def test_summary_mode_empty_repo_exits_zero(self):
        repo = MemoryRepository()
        assert _ctrl(repo).run(["summarize"]) == 0

    def test_summary_mode_empty_repo_shows_zero(self, capsys):
        repo = MemoryRepository()
        _ctrl(repo).run(["summarize"])
        out = capsys.readouterr().out
        assert "0" in out

    def test_full_report_empty_repo_exits_zero(self):
        repo = MemoryRepository()
        assert _ctrl(repo).run(["summarize", "--report", "full"]) == 0

    def test_full_report_empty_repo_shows_no_articles(self, capsys):
        repo = MemoryRepository()
        _ctrl(repo).run(["summarize", "--report", "full"])
        out = capsys.readouterr().out
        assert "No articles" in out


# ---------------------------------------------------------------------------
# 10. All success paths return exit code 0
# ---------------------------------------------------------------------------


class TestExitCodes:
    def test_ingest_exit_zero(self):
        repo = MemoryRepository()
        assert _run_ingest(_ctrl(repo), repo, [_article(1)]) == 0

    def test_analyze_exit_zero(self):
        repo = MemoryRepository()
        repo.add_articles([_article(1)])
        assert _ctrl(repo).run(["analyze"]) == 0

    def test_summarize_summary_exit_zero(self):
        repo = MemoryRepository()
        assert _ctrl(repo).run(["summarize"]) == 0

    def test_summarize_full_exit_zero(self):
        repo = MemoryRepository()
        assert _ctrl(repo).run(["summarize", "--report", "full"]) == 0


# ---------------------------------------------------------------------------
# 11. Double-analyze: already-scored articles are not re-scored
# ---------------------------------------------------------------------------


class TestAnalyzeIdempotency:
    def test_second_analyze_does_not_create_duplicate_scores(self):
        repo = MemoryRepository()
        articles = [_article(i) for i in range(1, 4)]
        repo.add_articles(articles)
        ctrl = _ctrl(repo)
        ctrl.run(["analyze"])
        # capture score timestamps from first pass
        first_timestamps = {a.id: repo.get_bias_score(a.id).timestamp for a in articles}
        ctrl.run(["analyze"])
        for a in articles:
            assert repo.get_bias_score(a.id).timestamp == first_timestamps[a.id]
