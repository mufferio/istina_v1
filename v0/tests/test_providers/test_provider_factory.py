"""
Provider Factory tests.

Goal:
- Test provider selection via different configuration sources
- Verify ISTINA_PROVIDER environment variable works correctly 
- Test error handling for invalid/missing providers
- Verify MockProvider is returned when ISTINA_PROVIDER=mock
"""

import os
import pytest
from unittest.mock import patch

from istina.config.settings import Settings, load_settings
from istina.model.providers.provider_factory import create_provider, ConfigError
from istina.model.providers.mock_provider import MockProvider
from istina.model.providers.base_provider import BaseProvider


@pytest.fixture
def mock_settings():
    """Basic settings with mock provider."""
    return Settings(provider="mock")


@pytest.fixture  
def gemini_settings():
    """Settings configured for Gemini (will fail without implementation)."""
    return Settings(provider="gemini")


class TestProviderFactory:
    """Test the provider factory functionality."""

    def test_create_mock_provider_from_settings(self, mock_settings):
        """Test creating MockProvider from settings object."""
        provider = create_provider(mock_settings)
        
        assert isinstance(provider, MockProvider)
        assert isinstance(provider, BaseProvider)
        assert provider.provider_name == "mock"

    def test_create_provider_from_dict_settings(self):
        """Test creating provider from dictionary-style settings."""
        settings_dict = {"provider": "mock"}
        provider = create_provider(settings_dict)
        
        assert isinstance(provider, MockProvider)
        assert provider.provider_name == "mock"

    def test_create_provider_defaults_to_mock_when_no_settings(self):
        """Test that MockProvider is created when no settings provided."""
        provider = create_provider(None)
        assert isinstance(provider, MockProvider)

    def test_create_provider_defaults_to_mock_when_provider_missing(self):
        """Test that MockProvider is created when provider field missing."""
        settings = Settings(env="test")  # provider not explicitly set
        provider = create_provider(settings)
        assert isinstance(provider, MockProvider)

    def test_provider_name_case_insensitive(self):
        """Test that provider names are case insensitive."""
        test_cases = ["mock", "MOCK", "Mock", "mOcK"]
        
        for provider_name in test_cases:
            settings = Settings(provider=provider_name)
            provider = create_provider(settings)
            assert isinstance(provider, MockProvider)

    def test_provider_name_strips_whitespace(self):
        """Test that provider names with whitespace are handled."""
        settings = Settings(provider="  mock  ")
        provider = create_provider(settings)
        assert isinstance(provider, MockProvider)

    def test_gemini_provider_fails_without_api_key(self, gemini_settings):
        """Test that Gemini provider requires API key."""
        with pytest.raises(ValueError, match="gemini_api_key is required to instantiate GeminiProvider"):
            create_provider(gemini_settings)

    def test_invalid_provider_raises_error(self):
        """Test that invalid provider names raise ConfigError."""
        settings = Settings(provider="invalid_provider")
        
        with pytest.raises(ConfigError, match="Unsupported provider: 'invalid_provider'"):
            create_provider(settings)

    def test_empty_provider_defaults_to_mock(self):
        """Test that empty provider string defaults to mock."""
        settings = Settings(provider="")
        provider = create_provider(settings)
        assert isinstance(provider, MockProvider)


class TestEnvironmentVariableIntegration:
    """Test that ISTINA_PROVIDER environment variable works correctly."""
    
    def test_istina_provider_env_var_mock_through_settings(self):
        """Test that ISTINA_PROVIDER=mock creates MockProvider through Settings."""
        with patch.dict(os.environ, {"ISTINA_PROVIDER": "mock"}):
            settings = load_settings()
            provider = create_provider(settings)
            
            assert isinstance(provider, MockProvider)
            assert settings.provider == "mock"

    def test_istina_provider_env_var_case_insensitive_through_settings(self):
        """Test ISTINA_PROVIDER environment variable is case insensitive."""
        test_cases = ["mock", "MOCK", "Mock", "mOcK"]
        
        for env_value in test_cases:
            with patch.dict(os.environ, {"ISTINA_PROVIDER": env_value}):
                settings = load_settings()
                provider = create_provider(settings)
                
                assert isinstance(provider, MockProvider)
                assert settings.provider.lower() == "mock"

    def test_default_provider_when_env_var_not_set(self):
        """Test default provider when ISTINA_PROVIDER not set."""
        # Ensure ISTINA_PROVIDER is not set
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings()
            provider = create_provider(settings)
            
            assert isinstance(provider, MockProvider)
            assert settings.provider == "mock"  # default from settings

    def test_invalid_env_var_through_settings_validation(self):
        """Test that invalid ISTINA_PROVIDER values are caught by settings validation.""" 
        with patch.dict(os.environ, {"ISTINA_PROVIDER": "invalid_provider"}):
            settings = load_settings()
            
            # Settings validation should catch this
            from istina.config.settings import validate_settings
            with pytest.raises(Exception):  # ConfigError or ValueError
                validate_settings(settings)

    @patch.dict(os.environ, {"ISTINA_PROVIDER": "mock"})
    def test_env_var_overrides_defaults(self):
        """Test that environment variable overrides default settings."""
        settings = load_settings()
        
        assert settings.provider == "mock"
        
        provider = create_provider(settings)
        assert isinstance(provider, MockProvider)

    def test_duck_typed_settings_object(self):
        """Test provider factory works with duck-typed settings objects."""
        
        class DuckTypedSettings:
            def __init__(self):
                self._data = {"provider": "mock"}
            
            def get(self, key, default=None):
                return self._data.get(key, default)
        
        settings = DuckTypedSettings()
        provider = create_provider(settings)
        assert isinstance(provider, MockProvider)


class TestProviderFactoryEdgeCases:
    """Test edge cases and error conditions."""

    def test_none_provider_value(self):
        """Test handling of None provider value."""
        
        class SettingsWithNoneProvider:
            provider = None
        
        settings = SettingsWithNoneProvider()
        provider = create_provider(settings)
        assert isinstance(provider, MockProvider)  # Should default to mock

    def test_numeric_provider_value_converted_to_string(self):
        """Test that numeric provider values are converted to strings."""
        
        class SettingsWithNumericProvider:
            provider = 123
        
        settings = SettingsWithNumericProvider()
        
        with pytest.raises(ConfigError, match="Unsupported provider: '123'"):
            create_provider(settings)

    def test_object_without_provider_attribute(self):
        """Test handling object that doesn't have provider attribute."""
        
        class EmptySettings:
            pass
        
        settings = EmptySettings()
        provider = create_provider(settings)
        assert isinstance(provider, MockProvider)  # Should default to mock