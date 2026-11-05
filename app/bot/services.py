"""Зависимости бота, собираемые в одной точке входа."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import utc_now
from app.config import Settings
from app.payments.base import PaymentProvider
from app.payments.factory import build_payment_provider
from app.storage.base import Storage
from app.storage.local import LocalStorage


@dataclass(frozen=True)
class BotServices:
    """Всё, что нужно хендлерам, передаётся явно."""

    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    storage: Storage
    payments: PaymentProvider
    now: Callable[[], datetime] = utc_now


def build_bot_services(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> BotServices:
    """Собирает боевые зависимости бота из настроек."""
    return BotServices(
        settings=settings,
        session_factory=session_factory,
        storage=LocalStorage(settings.storage_dir),
        payments=build_payment_provider(settings),
    )
