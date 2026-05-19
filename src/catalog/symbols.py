"""Deterministic public-symbol extraction.

Python is supported natively via stdlib ``ast``. Other languages currently
return an empty symbol list — the file still appears in the catalog with a
Haiku-generated purpose line. Add per-language extractors here later.
"""

from __future__ import annotations

import ast
import copy
from pathlib import Path

from src.schemas import CatalogSymbol


def _signature_via_unparse(node: ast.AST, fallback: str) -> str:
    """Render the signature line of a function/class via ``ast.unparse``.

    Copies the node, strips its body + decorators, unparses, takes the first
    line and drops the trailing colon. Falls back to ``fallback`` if anything
    in ast.unparse misbehaves on the input.
    """
    stub = copy.copy(node)
    stub.body = [ast.Pass()]
    stub.decorator_list = []
    try:
        text = ast.unparse(stub)
    except (AttributeError, TypeError, ValueError):
        return fallback
    first = text.splitlines()[0] if text else ""
    return first.rstrip(":").rstrip() or fallback


def _docstring_first_line(node: ast.AST) -> str:
    doc = ast.get_docstring(node)
    if not doc:
        return ""
    return doc.strip().splitlines()[0].strip()


def extract_python_symbols(source: str) -> list[CatalogSymbol]:
    """Return public top-level functions/classes/constants from a Python source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    out: list[CatalogSymbol] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            out.append(
                CatalogSymbol(
                    name=node.name,
                    signature=_signature_via_unparse(node, f"{prefix} {node.name}(...)"),
                    summary=_docstring_first_line(node),
                )
            )
        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            out.append(
                CatalogSymbol(
                    name=node.name,
                    signature=_signature_via_unparse(node, f"class {node.name}"),
                    summary=_docstring_first_line(node),
                )
            )
    return out


def extract_symbols(path: Path, source: str) -> list[CatalogSymbol]:
    """Dispatch by extension. Returns [] for unsupported languages."""
    if path.suffix == ".py":
        return extract_python_symbols(source)
    return []
