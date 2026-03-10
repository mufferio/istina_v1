"""
BaseCommand interface.

Purpose:
- Standardise how CLI commands are executed via the Command pattern.
- Decouple the CLI controller from command implementation details.

Contract:
    Every command must implement:

        def execute(self) -> CommandResult[T]:
            ...

    where T is the command-specific payload type:
        - IngestCommand    → CommandResult[IngestResult]
        - AnalyzeCommand   → CommandResult[AnalyzeResult]
        - SummarizeCommand → CommandResult[str]

Return value — CommandResult[T]:
    A lightweight envelope returned by every command:

        success: bool          — True if the command completed without error.
        data:    T | None      — The command payload on success; None on failure.
        message: str | None    — Human-readable summary (shown by CLI controller).
        error:   str | None    — Error description on failure; None on success.

    Using an envelope (rather than raising exceptions out of execute()) lets the
    CLI controller handle all output and exit-code logic in one place without
    wrapping every call in try/except.

Dependencies:
    Inject services, settings, and renderers through the constructor so that
    execute() is a pure call with no hidden globals.  This also makes commands
    trivially testable by passing fakes/stubs via __init__.

Error handling:
    - Domain/validation errors should be caught inside execute() and returned as
      CommandResult(success=False, error="...").
    - Truly unexpected errors (bugs) may propagate; the CLI controller owns the
      final catch-all and exit-code mapping.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass
class CommandResult(Generic[T]):
    """
    Typed envelope returned by every BaseCommand.execute() call.

    Attributes:
        success: Whether the command completed without error.
        data:    Command-specific payload (e.g. AnalyzeResult, str). None on failure.
        message: Short human-readable summary for the CLI to print.
        error:   Error description when success=False; None otherwise.

    Typical usage in a command::

        return CommandResult(success=True, data=result, message=f"Analyzed {n} articles.")

    Typical usage in the CLI controller::

        result = command.execute()
        if result.success:
            print(result.message)
        else:
            print(f"Error: {result.error}", file=sys.stderr)
            sys.exit(1)
    """

    success: bool
    data: Optional[T] = field(default=None)
    message: Optional[str] = field(default=None)
    error: Optional[str] = field(default=None)


class BaseCommand(ABC, Generic[T]):
    """
    Abstract base for all CLI commands.

    Subclasses:
        - Receive all dependencies via __init__ (services, settings, renderers).
        - Implement execute() to run the use-case and return a CommandResult[T].

    Example::

        class IngestCommand(BaseCommand[IngestResult]):
            def __init__(self, service: IngestService, feeds: list[str]):
                self._service = service
                self._feeds = feeds

            def execute(self) -> CommandResult[IngestResult]:
                result = self._service.ingest(self._feeds)
                return CommandResult(
                    success=True,
                    data=result,
                    message=f"Ingested {result.ingested_count} articles.",
                )
    """

    @abstractmethod
    def execute(self) -> CommandResult[T]:
        """
        Run the command and return a typed result envelope.

        Returns:
            CommandResult[T] with success=True and a populated data field on
            success, or success=False with an error message on failure.
        """
        ...
