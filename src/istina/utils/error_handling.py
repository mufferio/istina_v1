"""
Central error handling and app-level exceptions.

Purpose:
- Define custom exceptions:
  - ConfigError
  - RepositoryError
  - ProviderError
  - AdapterError
  - ValidationError
- Provide helper to format user-friendly CLI errors.

Used by:
- controller to print consistent errors without stack traces in normal mode.
"""

from __future__ import annotations

import traceback as _traceback


class ConfigError(ValueError):
    """Raised when configuration is missing or invalid."""


class RepositoryError(RuntimeError):
    """Raised when a repository operation fails."""


class ProviderError(RuntimeError):
    """Raised when an AI provider call fails."""


class AdapterError(RuntimeError):
    """Raised when an external adapter (e.g. RSS) fails to fetch or parse data."""


class ValidationError(ValueError):
    """Raised when domain-level validation fails."""


def format_error(exc: BaseException, *, verbose: bool = False) -> str:
    """
    Format an exception as a user-friendly CLI error string.

    Args:
        exc:     The exception to format.
        verbose: If True, include the exception type prefix.
                 If False (default), return just the message — suitable for
                 printing to stderr without a stack trace.

    Returns:
        A single-line string describing the error.

    Example::

        try:
            ...
        except Exception as e:
            print(format_error(e), file=sys.stderr)
            sys.exit(1)
    """
    msg = str(exc).strip() or repr(exc)
    if verbose:
        return f"[{type(exc).__name__}] {msg}"
    return msg


def format_exception(exc: BaseException, *, debug: bool = False) -> str:
    """
    Format an exception for CLI output with optional full traceback.

    Args:
        exc:   The exception to format.
        debug: If True, include the complete traceback (suitable for
               ``--debug`` mode).  If False (default), delegate to
               :func:`format_error` for a single-line friendly message.

    Returns:
        A string ready to print to stderr.

    Example::

        except Exception as e:
            print(format_exception(e, debug=args.debug), file=sys.stderr)
            sys.exit(1)
    """
    if debug:
        return "".join(
            _traceback.format_exception(type(exc), exc, exc.__traceback__)
        ).rstrip()
    return format_error(exc, verbose=False)
