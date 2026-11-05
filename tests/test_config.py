"""Тесты загрузки и обязательности настроек."""

import pytest

from app.config import (
    ConfigError,
    load_settings,
    require_bot_token,
    require_engine_credentials,
)

REQUIRED_ENV = (
    "DATABASE_URL",
    "TG_BOT_TOKEN",
    "TG_ADMIN_IDS",
    "ENGINE",
    "HF_KEY_ID",
    "HF_KEY_SECRET",
    "LOG_LEVEL",
    "SALES_ENABLED",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> pytest.MonkeyPatch:
    monkeypatch.chdir(tmp_path)
    for name in REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_settings_fail_without_database_url(clean_env: pytest.MonkeyPatch) -> None:
    with pytest.raises(ConfigError) as error:
        load_settings()
    assert "DATABASE_URL" in str(error.value)


def test_settings_read_typed_values(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
    clean_env.setenv("TG_BOT_TOKEN", "123:secret")
    clean_env.setenv("TG_ADMIN_IDS", "1, 2")
    clean_env.setenv("SALES_ENABLED", "false")
    clean_env.setenv("LOG_LEVEL", "debug")

    settings = load_settings()

    assert settings.database_url == "postgresql+asyncpg://user:pass@localhost:5432/db"
    assert settings.tg_admin_ids == (1, 2)
    assert settings.sales_enabled is False
    assert settings.log_level == "DEBUG"
    assert settings.engine == "mock"
    assert settings.payment_provider == "stub"
    assert settings.tg_bot_token is not None
    assert settings.tg_bot_token.get_secret_value() == "123:secret"


def test_bot_token_is_required(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
    settings = load_settings()
    with pytest.raises(ConfigError, match="TG_BOT_TOKEN"):
        require_bot_token(settings)


def test_blank_bot_token_is_rejected(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
    clean_env.setenv("TG_BOT_TOKEN", "   ")
    settings = load_settings()
    with pytest.raises(ConfigError, match="TG_BOT_TOKEN"):
        require_bot_token(settings)


def test_mock_engine_needs_no_secrets(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
    settings = load_settings()
    require_engine_credentials(settings)


def test_higgsfield_engine_requires_keys(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
    clean_env.setenv("ENGINE", "higgsfield")
    settings = load_settings()
    with pytest.raises(ConfigError) as error:
        require_engine_credentials(settings)
    assert "HF_KEY_ID" in str(error.value)
    assert "HF_KEY_SECRET" in str(error.value)
