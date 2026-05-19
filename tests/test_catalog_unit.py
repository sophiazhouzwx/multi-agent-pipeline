"""Hermetic tests for the catalog's deterministic pieces.

Walker, symbol extractor, markdown renderer — none of these touch the LLM.
"""

from __future__ import annotations

from pathlib import Path

from src.catalog.catalog_md import render_catalog_md
from src.catalog.symbols import extract_python_symbols, extract_symbols
from src.catalog.walker import iter_files, sha256_of, sha256_of_text
from src.schemas import Catalog, CatalogFile, CatalogSymbol


# ---------------------------------------------------------------------------
# Walker
# ---------------------------------------------------------------------------
def _scaffold_repo(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("def f(): pass\n")
    (root / "src" / "_private.py").write_text("x = 1\n")
    (root / "README.md").write_text("# hi\n")
    (root / ".gitignore").write_text("ignored.txt\nbuild/\n")
    (root / "ignored.txt").write_text("skip me\n")
    (root / "build").mkdir()
    (root / "build" / "out.txt").write_text("artefact\n")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.pyc").write_text("bytecode")
    (root / ".venv").mkdir()
    (root / ".venv" / "lib.py").write_text("# venv\n")
    (root / "image.png").write_bytes(b"\x89PNG")  # unsupported extension


def test_iter_files_respects_gitignore_and_defaults(tmp_path: Path):
    _scaffold_repo(tmp_path)
    rels = sorted(str(p.relative_to(tmp_path)) for p in iter_files(tmp_path))
    assert "src/main.py" in rels
    assert "src/_private.py" in rels  # underscore prefix is for SYMBOLS, not files
    assert "README.md" in rels
    assert "ignored.txt" not in rels         # .gitignore
    assert "build/out.txt" not in rels        # .gitignore
    assert ".venv/lib.py" not in rels         # default exclusion
    assert "image.png" not in rels            # unsupported extension
    # No __pycache__/*.pyc
    assert all(".pyc" not in r for r in rels)


def test_iter_files_max_files(tmp_path: Path):
    _scaffold_repo(tmp_path)
    assert len(list(iter_files(tmp_path, max_files=2))) == 2


def test_hashing_is_stable(tmp_path: Path):
    p = tmp_path / "a.py"
    p.write_text("hello\n")
    assert sha256_of(p) == sha256_of_text("hello\n")


# ---------------------------------------------------------------------------
# Symbol extraction
# ---------------------------------------------------------------------------
def test_python_symbols_basic():
    src = '''
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


async def fetch(url: str, *, timeout: float = 5.0) -> bytes:
    return b""


class Lexer(BaseModel):
    """Tokenizer."""

    def tokenize(self) -> list[str]:
        return []


def _hidden():
    return 1


class _Internal:
    pass
'''
    syms = extract_python_symbols(src)
    names = [s.name for s in syms]
    assert names == ["add", "fetch", "Lexer"]
    by_name = {s.name: s for s in syms}
    assert "(a: int, b: int) -> int" in by_name["add"].signature
    assert by_name["add"].summary == "Add two integers."
    assert "async def fetch" in by_name["fetch"].signature
    assert "url: str" in by_name["fetch"].signature
    # ast.unparse drops the space around '=' for defaults — that's fine.
    assert "timeout: float=5.0" in by_name["fetch"].signature
    assert by_name["Lexer"].signature == "class Lexer(BaseModel)"
    assert by_name["Lexer"].summary == "Tokenizer."


def test_python_symbols_skips_invalid_source():
    assert extract_python_symbols("def broken(:\n    pass") == []


def test_extract_symbols_unsupported_extension(tmp_path: Path):
    p = tmp_path / "x.txt"
    assert extract_symbols(p, "anything") == []


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------
def test_render_catalog_md_smoke():
    cat = Catalog(
        repo_path=Path("/tmp/example"),
        git_commit="abcd123" + "0" * 33,
        files=[
            CatalogFile(
                path="src/lexer.py",
                purpose="tokenises source into Token records",
                public_symbols=[
                    CatalogSymbol(
                        name="tokenize",
                        signature="def tokenize(src: str) -> list[Token]",
                        summary="convenience wrapper",
                    )
                ],
                content_hash="aaaa",
            ),
            CatalogFile(
                path="src/cli.py",
                purpose="typer CLI entrypoint",
                public_symbols=[],
                content_hash="bbbb",
            ),
        ],
    )
    md = render_catalog_md(cat)
    assert md.startswith("# AGENT_CATALOG.md")
    assert "src/lexer.py" in md
    assert "tokenises source" in md
    assert "def tokenize(src: str) -> list[Token]" in md
    assert "convenience wrapper" in md
    assert "src/cli.py" in md
    assert "typer CLI entrypoint" in md
    # Tree section appears before Files section.
    assert md.index("## Tree") < md.index("## Files")
