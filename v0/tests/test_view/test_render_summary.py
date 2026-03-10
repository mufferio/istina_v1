"""
Tests for view.render_summary.render_summary().

Covers:
- Plain-dict input (primary requirement)
- SummaryReport DTO input (backward-compat)
- Header and counter lines always present
- Bias distribution section present / absent
- By-source section present / absent
- Zero-article edge case
- Sorted label / source output
"""

from __future__ import annotations

import pytest

from istina.controller.services.report_service import SummaryReport
from istina.view.render_summary import render_summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXED_DICT = {
    "total_articles": 42,
    "analyzed_count": 17,
    "counts_by_overall_label": {
        "center": 10,
        "left": 4,
        "right": 3,
    },
    "counts_by_source": {
        "CNN": 22,
        "BBC News": 20,
    },
}


# ---------------------------------------------------------------------------
# Dict input — structure verification
# ---------------------------------------------------------------------------

class TestRenderSummaryDict:
    """render_summary() called with a plain dict."""

    def test_header_present(self):
        result = render_summary(FIXED_DICT)
        assert "=== Istina Summary ===" in result

    def test_articles_line(self):
        result = render_summary(FIXED_DICT)
        assert "Articles : 42" in result

    def test_analyzed_line(self):
        result = render_summary(FIXED_DICT)
        assert "Analyzed : 17 / 42" in result

    def test_bias_section_heading(self):
        result = render_summary(FIXED_DICT)
        assert "Bias distribution:" in result

    def test_bias_labels_present(self):
        result = render_summary(FIXED_DICT)
        assert "center" in result
        assert "left" in result
        assert "right" in result

    def test_bias_counts_present(self):
        result = render_summary(FIXED_DICT)
        assert ": 10" in result
        assert ": 4" in result
        assert ": 3" in result

    def test_source_section_heading(self):
        result = render_summary(FIXED_DICT)
        assert "By source:" in result

    def test_source_names_present(self):
        result = render_summary(FIXED_DICT)
        assert "CNN" in result
        assert "BBC News" in result

    def test_labels_sorted_alphabetically(self):
        result = render_summary(FIXED_DICT)
        center_pos = result.index("center")
        left_pos = result.index("left")
        right_pos = result.index("right")
        assert center_pos < left_pos < right_pos

    def test_sources_sorted_alphabetically(self):
        result = render_summary(FIXED_DICT)
        bbc_pos = result.index("BBC News")
        cnn_pos = result.index("CNN")
        assert bbc_pos < cnn_pos

    def test_full_output_matches_snapshot(self):
        """Exact structure check against a known-good string."""
        result = render_summary(FIXED_DICT)
        lines = result.splitlines()
        assert lines[0] == "=== Istina Summary ==="
        assert lines[1] == "Articles : 42"
        assert lines[2] == "Analyzed : 17 / 42"
        # blank line before distribution
        assert lines[3] == ""
        assert lines[4] == "Bias distribution:"
        # 3 label lines (sorted: center, left, right)
        assert "center" in lines[5]
        assert "left" in lines[6]
        assert "right" in lines[7]
        # blank line before sources
        assert lines[8] == ""
        assert lines[9] == "By source:"
        # 2 source lines (sorted: BBC, CNN)
        assert "BBC News" in lines[10]
        assert "CNN" in lines[11]

    def test_returns_string(self):
        assert isinstance(render_summary(FIXED_DICT), str)


# ---------------------------------------------------------------------------
# Dict input — optional sections absent when empty
# ---------------------------------------------------------------------------

class TestRenderSummaryDictOptionalSections:

    def test_no_label_section_when_empty(self):
        data = {"total_articles": 5, "analyzed_count": 0}
        result = render_summary(data)
        assert "Bias distribution:" not in result

    def test_no_source_section_when_empty(self):
        data = {"total_articles": 5, "analyzed_count": 0}
        result = render_summary(data)
        assert "By source:" not in result

    def test_no_label_section_when_key_absent(self):
        data = {
            "total_articles": 5,
            "analyzed_count": 2,
            "counts_by_source": {"Reuters": 5},
        }
        result = render_summary(data)
        assert "Bias distribution:" not in result

    def test_zero_articles(self):
        data = {"total_articles": 0, "analyzed_count": 0}
        result = render_summary(data)
        assert "Articles : 0" in result
        assert "Analyzed : 0 / 0" in result


# ---------------------------------------------------------------------------
# SummaryReport DTO input (backward compat)
# ---------------------------------------------------------------------------

class TestRenderSummaryDTO:

    def _make_report(self, **kwargs) -> SummaryReport:
        defaults = dict(
            total_articles=10,
            analyzed_count=5,
            counts_by_overall_label={"left": 3, "center": 2},
            counts_by_source={"Reuters": 10},
        )
        defaults.update(kwargs)
        return SummaryReport(**defaults)

    def test_header_present(self):
        assert "=== Istina Summary ===" in render_summary(self._make_report())

    def test_articles_line(self):
        assert "Articles : 10" in render_summary(self._make_report())

    def test_analyzed_line(self):
        assert "Analyzed : 5 / 10" in render_summary(self._make_report())

    def test_bias_distribution_shown(self):
        result = render_summary(self._make_report())
        assert "Bias distribution:" in result
        assert "left" in result
        assert "center" in result

    def test_by_source_shown(self):
        result = render_summary(self._make_report())
        assert "By source:" in result
        assert "Reuters" in result

    def test_empty_dto(self):
        report = SummaryReport(
            total_articles=0,
            analyzed_count=0,
            counts_by_overall_label={},
            counts_by_source={},
        )
        result = render_summary(report)
        assert "Articles : 0" in result
        assert "Bias distribution:" not in result
        assert "By source:" not in result
