"""Сборка видео-движка по настройкам: mock сейчас, higgsfield — позже."""

from app.config import ConfigError, Settings
from app.engines.base import VideoEngine
from app.engines.mock import MockVideoEngine


def build_video_engine(settings: Settings) -> VideoEngine:
    """Возвращает движок из настроек; неподключённый движок — ошибка конфигурации."""
    if settings.engine == "mock":
        return MockVideoEngine(settings.storage_dir)
    raise ConfigError("ENGINE=higgsfield ещё не реализован: доступен только mock.")
