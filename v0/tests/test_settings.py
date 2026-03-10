from istina.config.settings import ConfigError, load_settings, validate_settings
import pytest

def test_settings_loads():
    s = load_settings()
    # This should not raise if settings are valid
    validate_settings(s)
    assert s.env == "dev"