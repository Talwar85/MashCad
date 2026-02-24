"""
Regression test for modeling facade exports.

If code imports symbols via `from modeling import X`, then `X` must be
available on the modeling package facade (`modeling/__init__.py`).
"""

from __future__ import annotations

import ast
from pathlib import Path

import modeling


def _collect_imported_modeling_names(repo_root: Path) -> set[str]:
    names: set[str] = set()
    for path in repo_root.rglob("*.py"):
        if ".git" in path.parts or ".venv" in path.parts:
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "modeling":
                for alias in node.names:
                    if alias.name != "*":
                        names.add(alias.name)
    return names


def test_modeling_facade_exports_cover_all_local_imports():
    repo_root = Path(__file__).resolve().parent.parent
    imported_names = _collect_imported_modeling_names(repo_root)

    missing = sorted(name for name in imported_names if not hasattr(modeling, name))
    assert not missing, (
        "modeling facade is missing imported names: " + ", ".join(missing)
    )
