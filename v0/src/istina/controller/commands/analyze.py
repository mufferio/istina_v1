"""
AnalyzeCommand.

Purpose:
- Implement: "istina analyze [--limit N] [--source X] [--since ISO_DATE]"
- Calls AnalysisService to:
  - select unscored Articles (with optional filters)
  - run visitor.visit(article) for each
  - persist BiasScores

Output:
- CommandResult[AnalyzeResult] with:
    data    = AnalyzeResult (analyzed/skipped/failed counts + errors)
    message = human-readable one-liner for the CLI controller to print
"""

from __future__ import annotations

from typing import Optional, Union

from istina.controller.commands.base_command import BaseCommand, CommandResult
from istina.controller.services.analysis_service import (
    AnalyzeResult,
    AnalysisService,
    SelectionParams,
)
from istina.model.visitors.article_visitor import ArticleVisitor


class AnalyzeCommand(BaseCommand[AnalyzeResult]):
    """
    CLI command: analyze unscored articles and persist BiasScores.

    Args:
        service:             AnalysisService wired with repo.
        visitor_or_provider: ArticleVisitor or BiasProvider to score articles.
                             AnalysisService auto-wraps a raw provider in ScoringVisitor.
        params:              Optional SelectionParams (limit, source, since filters).

    Example::

        cmd = AnalyzeCommand(
            service=analysis_svc,
            visitor_or_provider=MockProvider(),
            params=SelectionParams(limit=10),
        )
        result = cmd.execute()
        # result.data    -> AnalyzeResult(analyzed_count=10, ...)
        # result.message -> "Analyzed 10 articles. Skipped: 0. Failed: 0."
    """

    def __init__(
        self,
        service: AnalysisService,
        visitor_or_provider: Union[ArticleVisitor, object],
        params: Optional[SelectionParams] = None,
    ) -> None:
        self._service = service
        self._visitor_or_provider = visitor_or_provider
        self._params = params

    def execute(self) -> CommandResult[AnalyzeResult]:
        """
        Run analysis on unscored articles and store the results.

        Returns:
            CommandResult[AnalyzeResult]:
                success=True  when the run completes (partial failures are
                              recorded in data.errors).
                success=False only on an unexpected top-level exception.
        """
        try:
            result = self._service.analyze(
                visitor_or_provider=self._visitor_or_provider,
                params=self._params,
            )
        except Exception as exc:
            return CommandResult(
                success=False,
                error=f"Analysis failed unexpectedly: {exc}",
            )

        msg = (
            f"Analyzed {result.analyzed_count} articles. "
            f"Skipped: {result.skipped_count}. "
            f"Failed: {result.failed_count}."
        )
        if result.errors:
            msg += f" ({len(result.errors)} error(s) recorded)"

        return CommandResult(
            success=True,
            data=result,
            message=msg,
        )
