"""
CLI summary renderer.

Purpose:
- Produce concise terminal output:
  - number of articles ingested
  - how many analyzed
  - top sources
  - quick bias distribution overview

Input:
- SummaryReport DTO from ReportService  **or**
- A plain dict with the same keys (useful for testing and ad-hoc use):
    {
        "total_articles": int,
        "analyzed_count": int,
        "counts_by_overall_label": dict[str, int],  # optional
        "counts_by_source": dict[str, int],          # optional
    }

Output:
- Formatted string (print-ready text block).
"""

from __future__ import annotations

from typing import Union

from istina.controller.services.report_service import SummaryReport


def render_summary(report: Union[SummaryReport, dict]) -> str:
    """
    Render a concise summary of repo state.

    Args:
        report: Either a ``SummaryReport`` produced by
                ``ReportService.get_summary()``, or a plain :class:`dict`
                with the same keys (``total_articles``, ``analyzed_count``,
                ``counts_by_overall_label``, ``counts_by_source``).

    Returns:
        A multi-line formatted string ready to print to the terminal.

    Example output::

        === Istina Summary ===
        Articles : 42
        Analyzed : 17 / 42

        Bias distribution:
          center   : 10
          left     :  4
          right    :  3

        By source:
          BBC News             : 20
          CNN                  : 22
    """
    # Normalise: accept both SummaryReport dataclass and plain dict so that
    # callers in tests (or ad-hoc scripts) can pass a raw dict without needing
    # to construct the full DTO.
    if isinstance(report, dict):
        total = report.get("total_articles", 0)
        analyzed = report.get("analyzed_count", 0)
        by_label: dict = report.get("counts_by_overall_label") or {}
        by_source: dict = report.get("counts_by_source") or {}
    else:
        total = report.total_articles
        analyzed = report.analyzed_count
        by_label = report.counts_by_overall_label or {}
        by_source = report.counts_by_source or {}

    lines: list[str] = []
    lines.append("=== Istina Summary ===")
    lines.append(f"Articles : {total}")
    lines.append(f"Analyzed : {analyzed} / {total}")

    if by_label:
        lines.append("")
        lines.append("Bias distribution:")
        for label, count in sorted(by_label.items()):
            lines.append(f"  {label:<8}: {count}")

    if by_source:
        lines.append("")
        lines.append("By source:")
        for source, count in sorted(by_source.items()):
            lines.append(f"  {source:<20}: {count}")

    return "\n".join(lines)
