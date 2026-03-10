"""
Tests for view.render_report

Covers render_report(article, bias_score) -> str  (single-article, primary API)
and render_full_report(pairs) -> str              (multi-article wrapper).

Verification strategy:
- Fixed Article + BiasScore objects → exact structural assertions
- Each section (header, metadata, bias, flags, claims, citations) tested
  individually and together as a snapshot
- Missing BiasScore → graceful "NOT ANALYZED" path
- Edge cases: empty claims, empty evidence, empty flags, empty pairs list
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore
from istina.view.render_report import render_full_report, render_report

# ---------------------------------------------------------------------------
# Fixed fixtures
# ---------------------------------------------------------------------------

_TS = datetime(2026, 1, 10, 9, 0, 0, tzinfo=timezone.utc)


def _make_article(
    *,
    title: str = "Scientists discover new energy source",
    url: str = "https://example.com/energy",
    source: str = "Science Daily",
    published_at: str = "2026-01-10T09:00:00Z",
) -> Article:
    return Article.create(
        title=title,
        url=url,
        source=source,
        published_at=published_at,
    )


def _make_score(
    *,
    article_id: str | None = None,
    label: str = "center",
    confidence: float = 0.82,
    flags: list | None = None,
    claims: list | None = None,
) -> BiasScore:
    aid = article_id or Article.compute_id(
        url="https://example.com/energy",
        source="Science Daily",
        published_at="2026-01-10T09:00:00Z",
    )
    return BiasScore(
        article_id=aid,
        provider="mock",
        overall_bias_label=label,
        confidence=confidence,
        rhetorical_bias=flags if flags is not None else ["loaded language", "framing"],
        claim_checks=claims
        if claims is not None
        else [
            {
                "claim": "Renewable energy output doubled in 2025",
                "verdict": "true",
                "confidence": 0.87,
                "evidence": [
                    "https://energy-stats.example.com/2025",
                    "IEA World Energy Outlook 2025, p. 42",
                ],
            }
        ],
        timestamp=_TS,
    )


# ---------------------------------------------------------------------------
# Single-article render_report — with score
# ---------------------------------------------------------------------------


class TestRenderReportWithScore:
    def setup_method(self):
        self.article = _make_article()
        self.score = _make_score()
        self.result = render_report(self.article, self.score)

    def test_returns_string(self):
        assert isinstance(self.result, str)

    def test_header_present(self):
        assert "=== Article Report ===" in self.result

    def test_title_shown(self):
        assert "Scientists discover new energy source" in self.result

    def test_url_shown(self):
        assert "https://example.com/energy" in self.result

    def test_source_shown(self):
        assert "Science Daily" in self.result

    def test_date_shown(self):
        assert "2026-01-10T09:00:00Z" in self.result

    def test_bias_label_shown(self):
        assert "center" in self.result

    def test_confidence_shown(self):
        assert "0.82" in self.result

    def test_flags_shown(self):
        assert "loaded language" in self.result
        assert "framing" in self.result

    def test_claims_section_heading(self):
        assert "Claims :" in self.result

    def test_claim_text_shown(self):
        assert "Renewable energy output doubled in 2025" in self.result

    def test_claim_verdict_shown(self):
        assert "verdict: true" in self.result

    def test_claim_confidence_shown(self):
        assert "0.87" in self.result

    def test_citations_heading_shown(self):
        assert "Citations:" in self.result

    def test_citation_url_shown(self):
        assert "https://energy-stats.example.com/2025" in self.result

    def test_citation_text_shown(self):
        assert "IEA World Energy Outlook 2025, p. 42" in self.result

    def test_not_analyzed_absent(self):
        assert "NOT ANALYZED" not in self.result

    def test_snapshot_line_order(self):
        """Structural ordering: header → metadata → bias → flags → claims."""
        lines = self.result.splitlines()
        header_idx = next(i for i, l in enumerate(lines) if "=== Article Report ===" in l)
        title_idx = next(i for i, l in enumerate(lines) if "Title" in l)
        bias_idx = next(i for i, l in enumerate(lines) if "Bias" in l)
        claims_idx = next(i for i, l in enumerate(lines) if "Claims" in l)
        assert header_idx < title_idx < bias_idx < claims_idx


# ---------------------------------------------------------------------------
# Single-article render_report — missing BiasScore
# ---------------------------------------------------------------------------


class TestRenderReportNoScore:
    def setup_method(self):
        self.article = _make_article(title="Breaking news story", source="Wire")
        self.result = render_report(self.article, None)

    def test_not_analyzed_label(self):
        assert "NOT ANALYZED" in self.result

    def test_title_still_shown(self):
        assert "Breaking news story" in self.result

    def test_source_still_shown(self):
        assert "Wire" in self.result

    def test_bias_section_absent(self):
        # No confidence value — score is absent
        assert "confidence" not in self.result

    def test_claims_absent(self):
        assert "Claims" not in self.result

    def test_flags_absent(self):
        assert "Flags" not in self.result

    def test_returns_string(self):
        assert isinstance(self.result, str)


# ---------------------------------------------------------------------------
# Edge cases — optional fields
# ---------------------------------------------------------------------------


class TestRenderReportEdgeCases:
    def _article(self):
        return _make_article()

    def test_no_rhetorical_flags_shows_none(self):
        score = _make_score(flags=[])
        result = render_report(self._article(), score)
        assert "Flags  : none" in result

    def test_no_claims_shows_none(self):
        score = _make_score(claims=[])
        result = render_report(self._article(), score)
        assert "Claims : none" in result

    def test_claim_without_evidence_no_citations_heading(self):
        score = _make_score(
            claims=[{"claim": "A claim", "verdict": "mixed", "evidence": []}]
        )
        result = render_report(self._article(), score)
        assert "A claim" in result
        assert "Citations:" not in result

    def test_claim_with_evidence_shows_each_item(self):
        score = _make_score(
            claims=[
                {
                    "claim": "Claim with evidence",
                    "verdict": "unverified",
                    "evidence": ["Source A", "Source B", "Source C"],
                }
            ]
        )
        result = render_report(self._article(), score)
        assert "Source A" in result
        assert "Source B" in result
        assert "Source C" in result

    def test_missing_published_at_shows_unknown(self):
        article = Article.create(
            title="No date article",
            url="https://example.com/nodate",
            source="Unknown Source",
            published_at=None,
        )
        result = render_report(article, None)
        assert "unknown" in result

    def test_multiple_claims_all_shown(self):
        claims = [
            {"claim": f"Claim {i}", "verdict": "mixed", "evidence": []} for i in range(3)
        ]
        score = _make_score(claims=claims)
        result = render_report(self._article(), score)
        assert "Claim 0" in result
        assert "Claim 1" in result
        assert "Claim 2" in result

    def test_claim_missing_confidence_key_no_crash(self):
        """confidence key absent from claim dict → renders without crashing."""
        score = _make_score(
            claims=[{"claim": "No conf claim", "verdict": "true", "evidence": []}]
        )
        result = render_report(self._article(), score)
        assert "No conf claim" in result
        # No "(confidence: ...)" suffix when key is absent
        assert "confidence" not in result.split("verdict")[1].split("\n")[0]


# ---------------------------------------------------------------------------
# render_full_report — multi-article wrapper
# ---------------------------------------------------------------------------


class TestRenderFullReport:
    def _pair(self, title="Article A", analyzed=True):
        article = _make_article(
            title=title,
            url=f"https://example.com/{title.lower().replace(' ', '-')}",
            source="Reuters",
        )
        score = _make_score(article_id=article.id) if analyzed else None
        return (article, score)

    def test_empty_list_returns_no_articles(self):
        assert render_full_report([]) == "No articles found."

    def test_header_present(self):
        result = render_full_report([self._pair()])
        assert "=== Istina Full Report" in result

    def test_plural_articles(self):
        result = render_full_report([self._pair("A"), self._pair("B")])
        assert "2 articles" in result

    def test_singular_article(self):
        result = render_full_report([self._pair()])
        assert "1 article)" in result

    def test_index_numbers_shown(self):
        result = render_full_report([self._pair("First"), self._pair("Second")])
        assert "[1]" in result
        assert "[2]" in result

    def test_divider_shown(self):
        result = render_full_report([self._pair()])
        assert "---" in result

    def test_both_article_titles_present(self):
        result = render_full_report([self._pair("Alpha Article"), self._pair("Beta Article")])
        assert "Alpha Article" in result
        assert "Beta Article" in result

    def test_not_analyzed_article_in_full_report(self):
        result = render_full_report([self._pair("Unscored", analyzed=False)])
        assert "NOT ANALYZED" in result

    def test_article_report_content_embedded(self):
        """render_full_report should include per-article content from render_report."""
        result = render_full_report([self._pair("Reuters Exclusive")])
        assert "Reuters Exclusive" in result
        assert "center" in result  # from mock score label
