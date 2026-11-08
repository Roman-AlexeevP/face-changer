"""Продажи: пауза по сервисному флагу и решение, можно ли принимать заказы."""

from dataclasses import dataclass
from datetime import datetime, timedelta

SALES_BLOCK_FLAG = "sales_blocked_until"
SALES_PAUSE = timedelta(minutes=60)
NO_CREDITS_REASON = "no_credits"


@dataclass(frozen=True)
class Flag:
    """Сервисный флаг с необязательным сроком действия."""

    name: str
    value: str
    expires_at: datetime | None = None


def is_sales_open(flag: Flag | None, now: datetime) -> bool:
    """Продажи открыты, если флага нет, он пуст или уже истёк."""
    if flag is None or not flag.value.strip():
        return True
    if flag.expires_at is None:
        return False
    return flag.expires_at <= now


def build_sales_block(now: datetime) -> Flag:
    """Ставит паузу продаж на час; дальше она истекает сама."""
    return Flag(SALES_BLOCK_FLAG, NO_CREDITS_REASON, now + SALES_PAUSE)
