"""Архитектурный тест: чистое ядро не импортирует инфраструктуру."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_DIR = REPO_ROOT / "app" / "domain"
FORBIDDEN_MODULES = frozenset({"aiogram", "sqlalchemy", "httpx", "os", "time", "random", "uuid"})


def iter_domain_modules() -> list[Path]:
    return sorted(DOMAIN_DIR.rglob("*.py"))


def read_module_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def collect_imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(read_module_tree(path)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def collect_forbidden_imports() -> list[str]:
    violations: list[str] = []
    for path in iter_domain_modules():
        for module in sorted(collect_imported_modules(path)):
            if module.split(".")[0] in FORBIDDEN_MODULES:
                violations.append(f"{path.relative_to(REPO_ROOT)}: {module}")
    return violations


def test_domain_imports_only_pure_modules() -> None:
    assert DOMAIN_DIR.is_dir()
    assert iter_domain_modules()
    assert collect_forbidden_imports() == []
