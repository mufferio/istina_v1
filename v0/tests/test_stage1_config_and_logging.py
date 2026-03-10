import logging
from pathlib import Path

import pytest

from istina.config.settings import Settings, load_settings, validate_settings, ConfigError
from istina.utils.logger import configure_logger


def test_stage1_settings_defaults():
    s = Settings()
    assert s.env == "dev"
    assert s.provider == "mock"
    assert s.repo_type == "file"
    assert s.log_level == "INFO"


def test_stage1_load_settings_reads_dotenv_and_env(monkeypatch, tmp_path: Path):
    """
    This test creates a temporary .env and verifies load_settings() reads it.
    Then it verifies real env vars override .env values.
    """
    # Create temp project-like folder with a .env file
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "ISTINA_ENV=dev",
                "ISTINA_PROVIDER=mock",
                "ISTINA_REPO_TYPE=memory",
                "ISTINA_LOG_LEVEL=INFO",
                "ISTINA_DATA_DIR=./data",
                "ISTINA_RATE_LIMIT_RPM=60",
                "",
            ]
        )
    )

    # Run load_settings() from that directory so dotenv finds tmp .env
    monkeypatch.chdir(tmp_path)

    # Clear any ISTINA_* env vars that may be set in the outer shell so this
    # test only sees the values from the temp .env file above.
    for var in ("ISTINA_ENV", "ISTINA_PROVIDER", "ISTINA_REPO_TYPE",
                "ISTINA_LOG_LEVEL", "ISTINA_DATA_DIR", "ISTINA_RATE_LIMIT_RPM",
                "ISTINA_GEMINI_API_KEY", "ISTINA_GEMINI_MODEL"):
        monkeypatch.delenv(var, raising=False)

    s = load_settings()
    assert s.provider == "mock"
    assert s.repo_type == "file"
    assert s.log_level == "INFO"
    assert s.rate_limit_rpm == 60

    # Now override using environment variables (env vars should beat .env)
    monkeypatch.setenv("ISTINA_PROVIDER", "gemini")
    monkeypatch.setenv("ISTINA_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ISTINA_RATE_LIMIT_RPM", "15")

    s2 = load_settings()
    assert s2.provider == "gemini"
    assert s2.log_level == "DEBUG"
    assert s2.rate_limit_rpm == 15


def test_stage1_validation_rejects_bad_values():
    with pytest.raises(ConfigError):
        validate_settings(Settings(provider="not-a-provider"))

    with pytest.raises(ConfigError):
        validate_settings(Settings(repo_type="sqlite"))

    with pytest.raises(ConfigError):
        validate_settings(Settings(log_level="LOUD"))

    with pytest.raises(ConfigError):
        validate_settings(Settings(rate_limit_rpm=0))


def test_stage1_logger_configures_level_and_is_idempotent():
    # Use a DEBUG level so we can verify it sets correctly
    s = Settings(log_level="DEBUG")

    log1 = configure_logger(s)

    assert isinstance(log1, logging.Logger)
    assert log1.level == logging.DEBUG

    # Capture handler count (calling configure_logger again should not add a second handler)
    handlers_before = len(log1.handlers)
    log2 = configure_logger(s)
    handlers_after = len(log2.handlers)

    assert log2 is log1
    assert handlers_after == handlers_before

    # Ensure it won't double-log via root propagation
    assert log1.propagate is False
