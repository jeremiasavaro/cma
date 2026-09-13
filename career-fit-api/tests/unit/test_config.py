"""Unit tests for app.config.Settings and get_settings()."""

from app.config import Settings, get_settings


def test_settings_defaults() -> None:
    # Bypass the local .env file so we assert on the actual class defaults,
    # not whatever a developer's local environment happens to set.
    settings = Settings(_env_file=None)

    assert settings.APP_NAME == "Career Fit Intelligence API"
    assert settings.API_PREFIX == "/v1"
    assert settings.LLM_PROVIDER == "groq"
    assert settings.DEBUG is False
    assert settings.DEFAULT_ANALYSIS_LEVEL == "full"


def test_get_settings_returns_singleton() -> None:
    first = get_settings()
    second = get_settings()

    assert first is second
