"""
CLI report renderer.

Purpose:
- Produce detailed, readable reports:
  - per-article bias breakdown
  - extracted claims with verdicts + citations
  - rhetorical flags

Public API:
    render_report(article, bias_score) -> str
        Single-article report; the primary entry point for the task.

    render_full_report(pairs) -> str
        Multi-article wrapper that delegates to render_report() and adds
        numbered headers / dividers.  Used by SummarizeCommand in "full" mode.

Design:
- Pure functions — no I/O, no side effects.
- All formatting is stable for snapshot testing.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from istina.model.entities.article import Article
from istina.model.entities.bias_score import BiasScore

_DIVIDER = "-" * 60
_HEADER = "=== Article Report ==="


# ---------------------------------------------------------------------------
# Primary single-article renderer
# ---------------------------------------------------------------------------

def render_report(article: Article, score: Optional[BiasScore]) -> str:
    """
    Render a detailed report for a single article.

    Args:
        article: The :class:`Article` to describe.
        score:   The :class:`BiasScore` from analysis, or ``None`` if the
                 article has not been analyzed yet.

    Returns:
        A multi-line string ready to print to the terminal.

    Example output (with score)::

        === Article Report ===
        Title  : Scientists discover new energy source
        URL    : https://example.com/energy
        Source : Science Daily
        Date   : 2026-01-10T09:00:00Z

        Bias   : center   (confidence: 0.82)
        Flags  : loaded language, framing

        Claims :
          • Specific claim — verdict: true  (confidence: 0.85)
            Citations:
              - https://evidence-source.example.com/page1
              - Supporting context note

    Example output (no score)::

        === Article Report ===
        Title  : Breaking news story
        URL    : https://example.com/breaking
        Source : Wire
        Date   : 2026-01-11

        Bias   : NOT ANALYZED
    """
    lines: list[str] = [_HEADER]

    # --- article metadata ---
    lines.append(f"Title  : {article.title}")
    lines.append(f"URL    : {article.url}")
    lines.append(f"Source : {article.source}")
    lines.append(f"Date   : {article.published_at or 'unknown'}")

    lines.append("")  # blank line before analysis section

    # --- analysis section ---
    if score is None:
        lines.append("Bias   : NOT ANALYZED")
        return "\n".join(lines)

    lines.append(f"Bias   : {score.overall_bias_label:<8} (confidence: {score.confidence:.2f})")

    flags = ", ".join(score.rhetorical_bias) if score.rhetorical_bias else "none"
    lines.append(f"Flags  : {flags}")

    # --- claim checks ---
    lines.append("")
    if not score.claim_checks:
        lines.append("Claims : none")
    else:
        lines.append("Claims :")
        for claim in score.claim_checks:
            text = claim.get("claim", "?")
            verdict = claim.get("verdict", "?")
            conf = claim.get("confidence")
            conf_str = f"  (confidence: {conf:.2f})" if isinstance(conf, (int, float)) else ""
            lines.append(f"  \u2022 {text} \u2014 verdict: {verdict}{conf_str}")

            # citations / evidence strings
            evidence = claim.get("evidence") or []
            if evidence:
                lines.append("    Citations:")
                for item in evidence:
                    lines.append(f"      - {item}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Multi-article wrapper (used by SummarizeCommand in "full" mode)
# ---------------------------------------------------------------------------

def render_full_report(pairs: List[Tuple[Article, Optional[BiasScore]]]) -> str:
    """
    Render a numbered full report for a collection of articles.

    Delegates each article to :func:`render_report` and wraps the result
    with an index header and a horizontal divider.

    Args:
        pairs: List of ``(Article, BiasScore | None)`` from
               ``ReportService.get_full_report()``.

    Returns:
        A multi-line formatted string, or ``"No articles found."`` for an
        empty list.
    """
    if not pairs:
        return "No articles found."

    header = (
        f"=== Istina Full Report "
        f"({len(pairs)} article{'s' if len(pairs) != 1 else ''}) ==="
    )
    sections: list[str] = [header]

    for idx, (article, score) in enumerate(pairs, start=1):
        sections.append("")
        sections.append(_DIVIDER)
        sections.append(f"[{idx}]")
        # Indent each line of the single-article report by 4 spaces
        article_block = render_report(article, score)
        for line in article_block.splitlines():
            sections.append(f"    {line}" if line else "")

    return "\n".join(sections)
