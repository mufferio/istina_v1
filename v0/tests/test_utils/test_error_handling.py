"""
Tests for utils.error_handling

Covers:
- format_error: message only / verbose with type prefix
- format_exception: delegates to format_error when debug=False
- format_exception: returns full traceback string when debug=True
- Custom exception types importable and inherit correct bases
"""

from __future__ import annotations

import pytest

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
# format_error
# ---------------------------------------------------------------------------


class TestFormatError:
    def test_returns_message_in_normal_mode(self):
        exc = ValueError("something went wrong")
        assert format_error(exc) == "something went wrong"

    def test_verbose_includes_type_prefix(self):
        exc = ValueError("bad value")
        result = format_error(exc, verbose=True)
        assert result.startswith("[ValueError]")
        assert "bad value" in result

    def test_strips_whitespace(self):
        exc = ValueError("  padded  ")
        assert format_error(exc) == "padded"

    def test_falls_back_to_repr_for_empty_message(self):
        exc = ValueError("")
        result = format_error(exc)
        assert "ValueError" in result

    def test_works_for_custom_exceptions(self):
        exc = ConfigError("missing API key")
        assert "missing API key" in format_error(exc)


# ---------------------------------------------------------------------------
# format_exception — non-debug (default)
# ---------------------------------------------------------------------------


class TestFormatExceptionNonDebug:
    def test_returns_friendly_string(self):
        exc = ConfigError("bad config")
        result = format_exception(exc)
        assert result == "bad config"

    def test_no_traceback_in_normal_mode(self):
        try:
            raise RuntimeError("explosion")
        except RuntimeError as exc:
            result = format_exception(exc, debug=False)
        assert "Traceback" not in result
        assert "explosion" in result

    def test_no_type_prefix_in_normal_mode(self):
        exc = ProviderError("api limit reached")
        result = format_exception(exc)
        assert "[" not in result
        assert "api limit reached" in result


# ---------------------------------------------------------------------------
# format_exception — debug=True
# ---------------------------------------------------------------------------


class TestFormatExceptionDebug:
    def test_debug_includes_traceback_header(self):
        try:
            raise ConfigError("bad key")
        except ConfigError as exc:
            result = format_exception(exc, debug=True)
        assert "Traceback" in result

    def test_debug_includes_exception_type(self):
        try:
            raise ConfigError("bad key")
        except ConfigError as exc:
            result = format_exception(exc, debug=True)
        assert "ConfigError" in result

    def test_debug_includes_message(self):
        try:
            raise ConfigError("missing_api_key")
        except ConfigError as exc:
            result = format_exception(exc, debug=True)
        assert "missing_api_key" in result

    def test_debug_includes_file_reference(self):
        """A real traceback includes the filename where the exception was raised."""
        try:
            raise ProviderError("quota exceeded")
        except ProviderError as exc:
            result = format_exception(exc, debug=True)
        assert "test_error_handling.py" in result

    def test_debug_returns_string(self):
        exc = AdapterError("feed parse failed")
        assert isinstance(format_exception(exc, debug=True), str)

    def test_exc_without_traceback_still_works(self):
        """Exception created but not raised — no __traceback__ attached."""
        exc = ValidationError("bad input")
        result = format_exception(exc, debug=True)
        # Should not raise; may or may not include 'Traceback'
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Custom exception hierarchy
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    def test_config_error_is_value_error(self):
        assert issubclass(ConfigError, ValueError)

    def test_repository_error_is_runtime_error(self):
        assert issubclass(RepositoryError, RuntimeError)

    def test_provider_error_is_runtime_error(self):
        assert issubclass(ProviderError, RuntimeError)

    def test_adapter_error_is_runtime_error(self):
        assert issubclass(AdapterError, RuntimeError)

    def test_validation_error_is_value_error(self):
        assert issubclass(ValidationError, ValueError)

    def test_all_catchable_as_exception(self):
        for cls in (ConfigError, RepositoryError, ProviderError, AdapterError, ValidationError):
            with pytest.raises(Exception):
                raise cls("test")
