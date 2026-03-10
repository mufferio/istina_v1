"""
ProviderFactory.

Purpose:
- Central place to select and create a Provider implementation based on settings.

Inputs:
- settings.provider_name (e.g., "mock", "gemini")

Outputs:
- An instance implementing BaseProvider

Design goal:
- Switching providers should require no changes in services/controllers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from istina.model.providers.base_provider import BaseProvider
from istina.model.providers.mock_provider import MockProvider


class ConfigError(ValueError):
    """Raised when provider configuration is invalid."""


def _get_setting(settings: Any, key: str, default: Any = None) -> Any:
    """Helper to get a setting with error handling."""
    if settings is None:
        return default

    if isinstance(settings, dict):
        return settings.get(key, default)

    # dataclass/object style
    if hasattr(settings, key):
        return getattr(settings, key)

    # duck-typed .get(...)
    get = getattr(settings, "get", None)
    if callable(get):
        return get(key, default)

    return default


def create_provider(settings: Any) -> BaseProvider:
    """
    Factory function to create a provider instance based on settings.

    Args:
        settings: An object/dict containing configuration, expected to have 'provider' field.

    Returns:
        An instance of a class implementing BaseProvider.

    Raises:
        ConfigError: If the provider_name is missing or unrecognized.
    """
    provider_name = _get_setting(settings, "provider", "mock")
    if provider_name is None or not str(provider_name).strip():
        provider_name = "mock"

    provider_name = str(provider_name).strip().lower()

    if provider_name == "mock":
        return MockProvider()

    if provider_name == "gemini":
        # v0 stub: you can implement GeminiProvider later.
        # For now we raise a clear error if someone selects it without implementation.
        # If you already have a GeminiProvider, import and return it here.
        try:
            from istina.model.providers.gemini_provider import GeminiProvider
            from istina.utils.rate_limiter import RateLimiter
        except Exception as e:
            raise ConfigError(
                "provider=gemini selected but GeminiProvider is not implemented/available"
            ) from e

        # Create rate limiter based on settings
        rate_limit_rpm = _get_setting(settings, "rate_limit_rpm", 60)
        limiter = RateLimiter(rpm=rate_limit_rpm) if rate_limit_rpm > 0 else None

        # Use the from_settings class method for proper configuration
        return GeminiProvider.from_settings(settings, limiter=limiter)

    raise ConfigError(f"Unsupported provider: {provider_name!r}. Expected 'mock' or 'gemini'.")
    