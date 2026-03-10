import pytest
from istina.config.settings import Settings, validate_settings, ConfigError


def test_invalid_provider_raises():
    with pytest.raises(ConfigError):
        validate_settings(Settings(provider="nope"))


def test_invalid_repo_type_raises():
    with pytest.raises(ConfigError):
        validate_settings(Settings(repo_type="sqlite"))
