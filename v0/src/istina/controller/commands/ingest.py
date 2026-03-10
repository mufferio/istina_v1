"""
IngestCommand.

Purpose:
- Implement: "istina ingest --feeds <feed_url> [<feed_url> ...]"
- Calls IngestService to:
  - fetch RSS entries (via rss_adapter)
  - normalize into Articles
  - store them via repository

Output:
- CommandResult[IngestResults] with:
    data    = IngestResults (fetched/new/existing counts + errors)
    message = human-readable one-liner for the CLI controller to print
"""

from __future__ import annotations

from typing import List

from istina.controller.commands.base_command import BaseCommand, CommandResult
from istina.controller.services.ingest_service import IngestResults, IngestService


class IngestCommand(BaseCommand[IngestResults]):
    """
    CLI command: fetch RSS feeds and store articles in the repository.

    Args:
        service: IngestService (already wired with repo + adapter).
        feeds:   List of RSS feed URLs to ingest.

    Example::

        cmd = IngestCommand(service=ingest_svc, feeds=["https://feeds.bbc.co.uk/..."])
        result = cmd.execute()
        # result.data    -> IngestResults(fetched_count=10, new_count=8, ...)
        # result.message -> "Ingested 10 articles (8 new, 2 already known)."
    """

    def __init__(self, service: IngestService, feeds: List[str]) -> None:
        if not feeds:
            raise ValueError("IngestCommand requires at least one feed URL.")
        self._service = service
        self._feeds = feeds

    def execute(self) -> CommandResult[IngestResults]:
        """
        Fetch and store articles from the configured feed URLs.

        Returns:
            CommandResult[IngestResults]:
                success=True  even when some feeds fail partially
                              (errors are recorded in data.errors).
                success=False only on an unexpected top-level exception.
        """
        try:
            result = self._service.ingest(self._feeds)
        except Exception as exc:
            return CommandResult(
                success=False,
                error=f"Ingest failed unexpectedly: {exc}",
            )

        msg = (
            f"Ingested {result.fetched_count} articles "
            f"({result.new_count} new, {result.existing_count} already known)."
        )
        if result.errors:
            msg += f" Errors: {len(result.errors)}"

        return CommandResult(
            success=True,
            data=result,
            message=msg,
        )
