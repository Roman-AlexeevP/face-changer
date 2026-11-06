"""Сборка видео-движка по настройкам: mock или реальный Higgsfield."""

from pydantic import SecretStr

from app.config import Settings, require_engine_credentials
from app.engines.base import VideoEngine
from app.engines.higgsfield import HiggsfieldConfig, HiggsfieldVideoEngine
from app.engines.mock import MockVideoEngine
from app.engines.transport import HttpTransport


def build_video_engine(settings: Settings) -> VideoEngine:
    """Возвращает движок из настроек; без ключей Higgsfield — ошибка конфигурации."""
    if settings.engine == "mock":
        return MockVideoEngine(settings.storage_dir)
    return build_higgsfield_engine(settings)


def build_higgsfield_engine(settings: Settings) -> HiggsfieldVideoEngine:
    """Собирает реальный движок и его HTTP-транспорт из HF_* настроек."""
    require_engine_credentials(settings)
    config = build_higgsfield_config(settings)
    transport = HttpTransport(
        base_url=config.base_url,
        key_id=config.key_id,
        key_secret=config.key_secret,
        timeout_sec=config.timeout_sec,
    )
    return HiggsfieldVideoEngine(config, transport)


def build_higgsfield_config(settings: Settings) -> HiggsfieldConfig:
    return HiggsfieldConfig(
        base_url=settings.hf_base_url,
        model=settings.hf_model,
        upload_url=settings.hf_upload_url,
        key_id=secret_value(settings.hf_key_id),
        key_secret=secret_value(settings.hf_key_secret),
        timeout_sec=settings.hf_timeout_sec,
        poll_interval_sec=settings.hf_poll_interval_sec,
        poll_max_min=settings.hf_poll_max_min,
    )


def secret_value(secret: SecretStr | None) -> str:
    return secret.get_secret_value() if secret is not None else ""
