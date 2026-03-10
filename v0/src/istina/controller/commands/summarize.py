"""
SummarizeCommand.

Purpose:
- Implement: "istina summarize [--mode summary|full] [--article-id ID] [--source X] [--limit N]"
- Calls ReportService to load Articles + BiasScores, then delegates to
  view renderers for formatting.

Output:
- CommandResult[str] with:
    data    = fully-formatted report string (callers may print it directly)
    message = same as data (convenient for CLI controller)
"""

from __future__ import annotations

from typing import Literal, Optional

from istina.controller.commands.base_command import BaseCommand, CommandResult
from istina.controller.services.report_service import ReportService
from istina.view.render_report import render_full_report
from istina.view.render_summary import render_summary

ReportMode = Literal["summary", "full"]


class SummarizeCommand(BaseCommand[str]):
    """
    CLI command: render a summary or full report to a string.

    Args:
        service:    ReportService wired with repo.
        mode:       "summary" (default) or "full".
        article_id: If set, full-report scoped to a single article.
        source:     If set, filter articles by source.
        limit:      Max articles to include (None = all).

    Example::

        cmd = SummarizeCommand(service=report_svc, mode="summary")
        result = cmd.execute()
        print(result.data)
    """

    def __init__(
        self,
        service: ReportService,
        mode: ReportMode = "summary",
        article_id: Optional[str] = None,
        source: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> None:
        if mode not in ("summary", "full"):
            raise ValueError(f"Invalid report mode '{mode}'. Choose 'summary' or 'full'.")
        self._service = service
        self._mode = mode
        self._article_id = article_id
        self._source = source
        self._limit = limit

    def execute(self) -> CommandResult[str]:
        """
        Build and return the formatted report string.

        Returns:
            CommandResult[str]:
                success=True  with data = formatted string.
                success=False with error on unexpected failure.
        """
        try:
            if self._mode == "summary":
                report = self._service.get_summary(
                    source=self._source,
                    limit=self._limit,
                )
                text = render_summary(report)
            else:
                pairs = self._service.get_full_report(
                    article_id=self._article_id,
                    source=self._source,
                    limit=self._limit,
                )
                text = render_full_report(pairs)
        except Exception as exc:
            return CommandResult(
                success=False,
                error=f"Report generation failed: {exc}",
            )

        return CommandResult(
            success=True,
            data=text,
            message=text,
        )
