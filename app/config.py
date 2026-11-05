"""Типизированные настройки, читаемые только из окружения."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict, SettingsError


class ConfigError(RuntimeError):
    """Настройки не загружены; сообщение пригодно для вывода человеку."""


class Settings(BaseSettings):
    """Полный набор переменных окружения проекта."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    database_url: str

    tg_bot_token: SecretStr | None = None
    tg_webhook_secret: SecretStr | None = None
    tg_admin_ids: Annotated[tuple[int, ...], NoDecode] = ()

    engine: Literal["mock", "higgsfield"] = "mock"
    hf_key_id: SecretStr | None = None
    hf_key_secret: SecretStr | None = None
    hf_base_url: str = "https://api.higgsfield.ai"
    hf_model: str = ""
    hf_poll_interval_sec: int = 3
    hf_poll_max_min: int = 8

    price_kopecks: int = 29900
    credits_per_order: int = 1
    engine_credits_hint: int = 0
    daily_generation_cap: int = 30
    sales_enabled: bool = True
    job_timeout_min: int = 8
    job_stale_minutes: int = 12

    storage: Literal["local", "s3"] = "local"
    storage_dir: Path = Path("/data/tmp")
    storage_url_ttl_min: int = 15

    payment_provider: Literal["stub", "yookassa"] = "stub"
    yookassa_shop_id: SecretStr | None = None
    yookassa_secret_key: SecretStr | None = None

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator("tg_admin_ids", mode="before")
    @classmethod
    def parse_tg_admin_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(int(part) for part in value.replace(",", " ").split())
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        if isinstance(value, str):
            return value.upper()
        return value


def load_settings() -> Settings:
    try:
        return Settings()
    except (ValidationError, SettingsError) as error:
        raise ConfigError(describe_settings_error(error)) from error


def describe_settings_error(error: Exception) -> str:
    if isinstance(error, ValidationError):
        details = "\n".join(f"  - {describe_field_error(item)}" for item in error.errors())
    else:
        details = f"  - {error}"
    return f"Не удалось прочитать настройки:\n{details}"


def describe_field_error(item: dict[str, object]) -> str:
    location = ".".join(str(part) for part in item["loc"]).upper()
    message = str(item["msg"])
    if item["type"] == "missing":
        return f"{location}: обязательная переменная не задана"
    return f"{location}: {message}"


def require_bot_token(settings: Settings) -> str:
    token = settings.tg_bot_token
    if token is None or not token.get_secret_value().strip():
        raise ConfigError("Не задан TG_BOT_TOKEN: бот не может стартовать.")
    return token.get_secret_value()


def require_engine_credentials(settings: Settings) -> None:
    if settings.engine != "higgsfield":
        return
    secrets = {"HF_KEY_ID": settings.hf_key_id, "HF_KEY_SECRET": settings.hf_key_secret}
    missing = [name for name, value in secrets.items() if is_blank_secret(value)]
    if missing:
        raise ConfigError(f"Для ENGINE=higgsfield не заданы: {', '.join(missing)}.")


def is_blank_secret(value: SecretStr | None) -> bool:
    return value is None or not value.get_secret_value().strip()
