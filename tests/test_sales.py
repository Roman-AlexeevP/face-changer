"""Чистое правило: когда продажи открыты по сервисному флагу."""

from datetime import UTC, datetime, timedelta

from app.domain.sales import SALES_BLOCK_FLAG, Flag, build_sales_block, is_sales_open

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def test_missing_flag_keeps_sales_open() -> None:
    assert is_sales_open(None, NOW) is True


def test_empty_flag_keeps_sales_open() -> None:
    flag = Flag(SALES_BLOCK_FLAG, "   ", NOW + timedelta(minutes=10))
    assert is_sales_open(flag, NOW) is True


def test_expired_flag_opens_sales() -> None:
    flag = Flag(SALES_BLOCK_FLAG, "no_credits", NOW - timedelta(minutes=1))
    assert is_sales_open(flag, NOW) is True


def test_active_flag_blocks_sales() -> None:
    flag = Flag(SALES_BLOCK_FLAG, "no_credits", NOW + timedelta(minutes=1))
    assert is_sales_open(flag, NOW) is False


def test_flag_without_expiry_blocks_sales_forever() -> None:
    flag = Flag(SALES_BLOCK_FLAG, "manual")
    assert is_sales_open(flag, NOW) is False


def test_flag_is_open_at_exact_expiry_moment() -> None:
    flag = Flag(SALES_BLOCK_FLAG, "no_credits", NOW)
    assert is_sales_open(flag, NOW) is True


def test_build_sales_block_pauses_for_one_hour() -> None:
    flag = build_sales_block(NOW)
    assert flag.name == SALES_BLOCK_FLAG
    assert flag.value == "no_credits"
    assert flag.expires_at == NOW + timedelta(minutes=60)
    assert is_sales_open(flag, NOW) is False
    assert is_sales_open(flag, NOW + timedelta(minutes=60)) is True
