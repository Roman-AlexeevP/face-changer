"""Сборка платёжного провайдера по настройкам."""

from app.config import ConfigError, Settings
from app.payments.base import PaymentProvider
from app.payments.stub import StubPaymentProvider


def build_payment_provider(settings: Settings) -> PaymentProvider:
    """Stub для MVP; неподключённый провайдер — ошибка конфигурации."""
    if settings.payment_provider == "stub":
        return StubPaymentProvider()
    raise ConfigError(f"PAYMENT_PROVIDER={settings.payment_provider} ещё не реализован.")
