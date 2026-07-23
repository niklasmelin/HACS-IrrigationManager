"""Readability tests for production class and function docstrings."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "solar_irrigation"


def test_all_production_definitions_have_docstrings() -> None:
    """Require every production class, function, and method to have a docstring."""
    missing: list[str] = []
    for path in sorted(ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if ast.get_docstring(node) is None:
                    missing.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.name}")
    assert not missing, "Missing docstrings:\n" + "\n".join(missing)
