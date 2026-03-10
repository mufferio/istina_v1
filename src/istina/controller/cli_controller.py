"""
CLIController.

Purpose:
- Central dispatcher for CLI commands.
- Builds the argparse parser, maps subcommands to Command objects, and
  calls execute() on the correct command.

Responsibilities:
- Register available subcommands (ingest, analyze, summarize)
- Provide shared dependencies (services, settings, logger)
- Execute commands and handle errors consistently via error_handling.format_error

Future:
- This controller maps 1:1 to an API controller in v1 (web).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from typing import Optional, Sequence

from istina.config.settings import Settings
from istina.controller.commands.analyze import AnalyzeCommand
from istina.controller.commands.ingest import IngestCommand
from istina.controller.commands.summarize import SummarizeCommand
from istina.controller.services.analysis_service import AnalysisService, SelectionParams
from istina.controller.services.ingest_service import IngestService
from istina.controller.services.report_service import ReportService
from istina.model.providers.provider_factory import create_provider
from istina.model.repositories.base_repository import BaseRepository
from istina.model.repositories.memory_repository import MemoryRepository
from istina.utils.error_handling import (
    AdapterError,
    ConfigError,
    ProviderError,
    RepositoryError,
    ValidationError,
    format_error,
    format_exception,
)


# ---------------------------------------------------------------------------
# Parser construction
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argparse parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="istina",
        description="Istina — RSS ingestion, bias analysis, and reporting CLI.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Show full stack traces instead of friendly error messages.",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ---- ingest ----
    ingest_p = sub.add_parser(
        "ingest",
        help="Fetch RSS feeds and store articles.",
        description=(
            "Fetch one or more RSS feed URLs, parse them into Articles, "
            "and store them in the repository."
        ),
    )
    ingest_p.add_argument(
        "--feeds",
        nargs="+",
        required=True,
        metavar="URL",
        help="One or more RSS feed URLs to ingest.",
    )

    # ---- analyze ----
    analyze_p = sub.add_parser(
        "analyze",
        help="Analyze unscored articles and store BiasScores.",
        description=(
            "Select unscored articles from the repository, run the configured "
            "provider/visitor on each, and persist the resulting BiasScores."
        ),
    )
    analyze_p.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of articles to analyze.",
    )
    analyze_p.add_argument(
        "--source",
        default=None,
        metavar="SOURCE",
        help="Restrict analysis to articles from this source.",
    )
    analyze_p.add_argument(
        "--since",
        default=None,
        metavar="ISO_DATE",
        help="Restrict analysis to articles published after this ISO 8601 date (e.g. 2026-01-01).",
    )

    # ---- summarize ----
    summarize_p = sub.add_parser(
        "summarize",
        help="Print a summary or full report.",
        description=(
            "Render a summary or full per-article report from the repository."
        ),
    )
    summarize_p.add_argument(
        "--report",
        dest="mode",
        choices=["summary", "full"],
        default="summary",
        help="Report type: 'summary' (default) or 'full' per-article detail.",
    )
    summarize_p.add_argument(
        "--article-id",
        default=None,
        metavar="ID",
        help="Scope full report to a single article ID.",
    )
    summarize_p.add_argument(
        "--source",
        default=None,
        metavar="SOURCE",
        help="Restrict report to articles from this source.",
    )
    summarize_p.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of articles to include in the report.",
    )

    return parser


# ---------------------------------------------------------------------------
# CLIController
# ---------------------------------------------------------------------------

class CLIController:
    """
    Wires shared dependencies and dispatches parsed args to the right Command.

    Args:
        settings: Loaded and validated Settings object.
        repo:     Repository instance shared across all commands.

    Usage::

        settings = load_settings()
        repo     = MemoryRepository()
        ctrl     = CLIController(settings=settings, repo=repo)
        sys.exit(ctrl.run(sys.argv[1:]))
    """

    def __init__(self, settings: Settings, repo: BaseRepository) -> None:
        self._settings = settings
        self._repo = repo
        self._logger = logging.getLogger("istina")
        self._debug: bool = False  # updated in run() after arg parse

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, argv: Optional[Sequence[str]] = None) -> int:
        """
        Parse *argv* (defaults to sys.argv[1:]), build and execute the
        correct Command, then print the result.

        Returns:
            0 on success, 1 on failure.
        """
        parser = build_parser()
        args = parser.parse_args(argv)
        self._debug = getattr(args, "debug", False)

        try:
            return self._dispatch(args)
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            return 130
        except Exception as exc:  # unexpected bug
            if self._debug:
                print(format_exception(exc, debug=True), file=sys.stderr)
            else:
                print(
                    f"Unexpected error: {format_error(exc, verbose=True)}",
                    file=sys.stderr,
                )
            self._logger.exception("Unhandled exception in CLIController.run")
            return 1

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    def _print_error(self, exc: BaseException, *, prefix: str = "Error") -> None:
        """Print a formatted error to stderr, respecting --debug mode."""
        if self._debug:
            import traceback
            print(traceback.format_exc(), file=sys.stderr)
        else:
            print(f"{prefix}: {format_error(exc)}", file=sys.stderr)

    def _dispatch(self, args: argparse.Namespace) -> int:
        try:
            if args.command == "ingest":
                return self._run_ingest(args)
            if args.command == "analyze":
                return self._run_analyze(args)
            if args.command == "summarize":
                return self._run_summarize(args)
            # argparse guarantees we never reach here, but keep it defensive
            print(f"Unknown command: {args.command}", file=sys.stderr)
            return 1
        except ConfigError as exc:
            self._print_error(exc, prefix="Configuration error")
            return 1
        except ProviderError as exc:
            self._print_error(exc, prefix="Provider error")
            return 1
        except AdapterError as exc:
            self._print_error(exc, prefix="Adapter error")
            return 1
        except ValidationError as exc:
            self._print_error(exc, prefix="Validation error")
            return 1
        except RepositoryError as exc:
            self._print_error(exc, prefix="Repository error")
            return 1

    def _run_ingest(self, args: argparse.Namespace) -> int:
        service = IngestService(repo=self._repo)
        cmd = IngestCommand(service=service, feeds=args.feeds)
        result = cmd.execute()
        if result.success:
            print(result.message)
            if result.data and result.data.errors:
                for err in result.data.errors:
                    print(f"  [warning] {err}", file=sys.stderr)
            return 0
        print(f"Error: {result.error}", file=sys.stderr)
        return 1

    def _run_analyze(self, args: argparse.Namespace) -> int:
        since: Optional[datetime] = None
        if args.since:
            try:
                since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
            except ValueError as exc:
                print(f"Error: --since value is not a valid ISO date: {exc}", file=sys.stderr)
                return 1

        provider = create_provider(self._settings)
        service = AnalysisService(repo=self._repo)
        params = SelectionParams(limit=args.limit, source=args.source, since=since)
        cmd = AnalyzeCommand(service=service, visitor_or_provider=provider, params=params)

        result = cmd.execute()
        if result.success:
            print(result.message)
            if result.data and result.data.errors:
                for err in result.data.errors:
                    print(f"  [warning] {err}", file=sys.stderr)
            return 0
        print(f"Error: {result.error}", file=sys.stderr)
        return 1

    def _run_summarize(self, args: argparse.Namespace) -> int:
        service = ReportService(repo=self._repo)
        cmd = SummarizeCommand(
            service=service,
            mode=args.mode,
            article_id=args.article_id,
            source=args.source,
            limit=args.limit,
        )
        result = cmd.execute()
        if result.success:
            print(result.data)
            return 0
        print(f"Error: {result.error}", file=sys.stderr)
        return 1
