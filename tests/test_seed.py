"""Промпт шаблона: можно задать файлом рядом с видео, без правки кода."""

import os
from pathlib import Path

from app.db import seed

# Каждый процесс pytest (включая воркеры xdist) пишет в свой каталог:
# фиксированный путь даёт гонку между тестами.
SCRATCH = Path(".tmp") / f"seed-test-{os.getpid()}"


def write_prompt_file(text: str) -> Path:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    path = SCRATCH / "prompt.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_file_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.setattr(seed, "PROMPT_FILE", SCRATCH / "absent.txt")
    assert seed.resolve_prompt("базовый") == "базовый"


def test_prompt_is_read_from_file(monkeypatch) -> None:
    path = write_prompt_file("  свой промпт для Genjutsu \n")
    monkeypatch.setattr(seed, "PROMPT_FILE", path)
    assert seed.resolve_prompt("базовый") == "свой промпт для Genjutsu"


def test_blank_file_falls_back_to_default(monkeypatch) -> None:
    path = write_prompt_file("   \n\n")
    monkeypatch.setattr(seed, "PROMPT_FILE", path)
    assert seed.resolve_prompt("базовый") == "базовый"
