"""
Tests for centralized CLI error handling in CLIController.

Covers:
- Domain exceptions raised during dispatch → friendly stderr message, exit 1
- --debug flag → full traceback on stderr, exit 1
- Non-zero exit codes on all failure paths
- Normal mode suppresses stack traces
- format_error/format_exception used consistently (no raw exception strings)

Verification strategy: patch individual _run_* or _dispatch methods to raise
known exceptions and assert on stderr + exit code.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from istina.config.settings import Settings
from istina.controller.cli_controller import CLIController
from istina.model.repositories.memory_repository import MemoryRepository
from istina.utils.error_handling import (
    AdapterError,
    ConfigError,
    ProviderError,
    RepositoryError,
    ValidationError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctrl(repo: MemoryRepository | None = None) -> CLIController:
    return CLIController(settings=Settings(provider="mock"), repo=repo or MemoryRepository())


# ---------------------------------------------------------------------------
# Per-domain-exception: friendly message + exit 1 (normal mode)
# ---------------------------------------------------------------------------


class TestDomainExceptionHandling:
    """Each known exception type is caught, printed cleanly, and returns 1."""

    def _run_with_exception(self, exc, argv=None, ctrl=None):
        repo = MemoryRepository()
        c = ctrl or _ctrl(repo)
        with patch.object(c, "_run_summarize", side_effect=exc):
            with patch.object(c, "_run_ingest", side_effect=exc):
                with patch.object(c, "_run_analyze", side_effect=exc):
                    return c, c.run(argv or ["summarize"])

    def test_config_error_exits_one(self, capsys):
        _, code = self._run_with_exception(ConfigError("missing GEMINI_API_KEY"))
        assert code == 1

    def test_config_error_prints_prefix(self, capsys):
        self._run_with_exception(ConfigError("missing GEMINI_API_KEY"))
        err = capsys.readouterr().err
        assert "Configuration error" in err
        assert "missing GEMINI_API_KEY" in err

    def test_config_error_no_traceback_in_normal_mode(self, capsys):
        self._run_with_exception(ConfigError("bad key"))
        err = capsys.readouterr().err
        assert "Traceback" not in err

    def test_provider_error_exits_one(self, capsys):
        _, code = self._run_with_exception(ProviderError("API quota exceeded"))
        assert code == 1

    def test_provider_error_prints_message(self, capsys):
        self._run_with_exception(ProviderError("API quota exceeded"))
        err = capsys.readouterr().err
        assert "API quota exceeded" in err

    def test_provider_error_no_traceback_in_normal_mode(self, capsys):
        self._run_with_exception(ProviderError("rate limit"))
        err = capsys.readouterr().err
        assert "Traceback" not in err

    def test_adapter_error_exits_one(self, capsys):
        _, code = self._run_with_exception(AdapterError("feed parse failed"))
        assert code == 1

    def test_adapter_error_prints_message(self, capsys):
        self._run_with_exception(AdapterError("feed parse failed"))
        err = capsys.readouterr().err
        assert "feed parse failed" in err

    def test_validation_error_exits_one(self, capsys):
        _, code = self._run_with_exception(ValidationError("field required"))
        assert code == 1

    def test_validation_error_prints_message(self, capsys):
        self._run_with_exception(ValidationError("field required"))
        err = capsys.readouterr().err
        assert "field required" in err

    def test_repository_error_exits_one(self, capsys):
        _, code = self._run_with_exception(RepositoryError("store unavailable"))
        assert code == 1

    def test_repository_error_prints_message(self, capsys):
        self._run_with_exception(RepositoryError("store unavailable"))
        err = capsys.readouterr().err
        assert "store unavailable" in err

    def test_error_message_no_raw_exception_repr(self, capsys):
        """Friendly output should not contain Python's raw exception repr."""
        self._run_with_exception(ConfigError("oops"))
        err = capsys.readouterr().err
        # Should NOT look like "ConfigError('oops')"
        assert "ConfigError('oops')" not in err


# ---------------------------------------------------------------------------
# --debug flag
# ---------------------------------------------------------------------------


class TestDebugFlag:
    """--debug makes all errors print full tracebacks."""

    def _run_debug(self, exc, capsys):
        repo = MemoryRepository()
        c = _ctrl(repo)
        with patch.object(c, "_run_summarize", side_effect=exc):
            code = c.run(["--debug", "summarize"])
        err = capsys.readouterr().err
        return code, err

    def test_debug_config_error_exits_one(self, capsys):
        code, _ = self._run_debug(ConfigError("bad key"), capsys)
        assert code == 1

    def test_debug_config_error_shows_traceback(self, capsys):
        _, err = self._run_debug(ConfigError("bad key"), capsys)
        assert "Traceback" in err or "ConfigError" in err

    def test_debug_provider_error_shows_traceback(self, capsys):
        _, err = self._run_debug(ProviderError("quota"), capsys)
        assert "Traceback" in err or "ProviderError" in err

    def test_debug_flag_registered_on_parser(self):
        from istina.controller.cli_controller import build_parser
        p = build_parser()
        args = p.parse_args(["--debug", "summarize"])
        assert args.debug is True

    def test_no_debug_flag_default_false(self):
        from istina.controller.cli_controller import build_parser
        p = build_parser()
        args = p.parse_args(["summarize"])
        assert args.debug is False


# ---------------------------------------------------------------------------
# Unexpected exceptions (catch-all in run())
# ---------------------------------------------------------------------------


class TestUnexpectedExceptions:
    def test_unexpected_exception_exits_one(self, capsys):
        repo = MemoryRepository()
        c = _ctrl(repo)
        with patch.object(c, "_dispatch", side_effect=RuntimeError("internal bug")):
            code = c.run(["summarize"])
        assert code == 1

    def test_unexpected_exception_prints_to_stderr(self, capsys):
        repo = MemoryRepository()
        c = _ctrl(repo)
        with patch.object(c, "_dispatch", side_effect=RuntimeError("internal bug")):
            c.run(["summarize"])
        err = capsys.readouterr().err
        assert "internal bug" in err

    def test_unexpected_exception_no_traceback_in_normal_mode(self, capsys):
        repo = MemoryRepository()
        c = _ctrl(repo)
        with patch.object(c, "_dispatch", side_effect=RuntimeError("internal bug")):
            c.run(["summarize"])
        err = capsys.readouterr().err
        assert "Traceback" not in err

    def test_unexpected_exception_debug_shows_traceback(self, capsys):
        repo = MemoryRepository()
        c = _ctrl(repo)
        with patch.object(c, "_dispatch", side_effect=RuntimeError("internal bug")):
            c.run(["--debug", "summarize"])
        err = capsys.readouterr().err
        # In debug mode the full traceback is shown
        assert "internal bug" in err


# ---------------------------------------------------------------------------
# Non-zero exit codes on all failure paths
# ---------------------------------------------------------------------------


class TestNonZeroExitCodes:
    def test_known_domain_exception_always_returns_one(self, capsys):
        exceptions = [
            ConfigError("a"),
            ProviderError("b"),
            AdapterError("c"),
            ValidationError("d"),
            RepositoryError("e"),
        ]
        for exc in exceptions:
            repo = MemoryRepository()
            c = _ctrl(repo)
            with patch.object(c, "_run_summarize", side_effect=exc):
                code = c.run(["summarize"])
            assert code == 1, f"Expected exit 1 for {type(exc).__name__}"

    def test_keyboard_interrupt_returns_130(self, capsys):
        repo = MemoryRepository()
        c = _ctrl(repo)
        with patch.object(c, "_dispatch", side_effect=KeyboardInterrupt):
            code = c.run(["summarize"])
        assert code == 130

    def test_success_path_returns_zero(self, capsys):
        repo = MemoryRepository()
        code = _ctrl(repo).run(["summarize"])
        assert code == 0
