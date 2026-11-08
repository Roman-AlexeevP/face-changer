"""Нормализация кодов ошибок движка: наружу — только известный набор."""

PUBLIC_CODES = frozenset(
    {
        "timeout",
        "moderated",
        "no_credits",
        "engine_5xx",
        "network",
        "bad_input",
        "engine_failed",
        "unknown",
    }
)
INTERNAL_CODES = frozenset(
    {
        "engine_auth",
        "engine_bad_config",
        "rate_limited",
        "engine_unavailable",
        "internal",
        "template_missing",
        "delivery_failed",
    }
)
ALIASES = {
    "unknown_status": "unknown",
    "bad_response": "unknown",
}


def normalize_error_code(code: str) -> str:
    """Приводит код движка к публичному или известному внутреннему."""
    if code in ALIASES:
        return ALIASES[code]
    if code in PUBLIC_CODES or code in INTERNAL_CODES:
        return code
    return "unknown"
