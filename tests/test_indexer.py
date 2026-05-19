"""End-to-end indexer test using TestModel to stub Claude Haiku.

Exercises the full incremental-update path:
1. Initialise an empty git repo with a couple of Python files.
2. Run index_repo with TestModel returning a deterministic purpose line.
3. Assert sidecar + AGENT_CATALOG.md were created correctly.
4. Run index_repo AGAIN with NO override. If unchanged-file detection works,
   no LLM call is needed and the second pass succeeds even though the real
   summarizer (which would error without API credentials) is back in scope.
5. Modify one file. Override again. Confirm only the modified file gets
   re-summarized.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from git import Repo as GitRepo
from pydantic_ai.models.test import TestModel

from src.catalog.indexer import (
    CATALOG_MD,
    SIDECAR_DIR,
    SIDECAR_JSON,
    ensure_git_repo,
    index_repo,
    index_stats,
    load_catalog,
)
from src.catalog.summarizer import summarizer_agent

pytestmark = pytest.mark.asyncio


def _init_repo(root: Path) -> None:
    GitRepo.init(root)
    repo = GitRepo(root)
    (root / "src").mkdir()
    (root / "src" / "lexer.py").write_text(
        '"""Tokenizer module."""\n\ndef tokenize(s: str) -> list[str]:\n    return s.split()\n'
    )
    (root / "src" / "parser.py").write_text(
        '"""Parser module."""\n\ndef parse(tokens: list[str]) -> dict:\n    return {}\n'
    )
    (root / "README.md").write_text("# example\n")
    repo.git.add(A=True)
    repo.index.commit("initial")


async def test_first_index_builds_catalog_and_sidecar(tmp_path: Path):
    _init_repo(tmp_path)
    with summarizer_agent.override(model=TestModel(custom_output_text="stub purpose")):
        catalog = await index_repo(tmp_path)

    paths = sorted(f.path for f in catalog.files)
    assert paths == ["README.md", "src/lexer.py", "src/parser.py"]
    assert all(f.purpose == "stub purpose" for f in catalog.files)
    assert all(f.content_hash for f in catalog.files)

    # Sidecar JSON exists and round-trips.
    sidecar = tmp_path / SIDECAR_DIR / SIDECAR_JSON
    assert sidecar.exists()
    reloaded = load_catalog(tmp_path)
    assert reloaded == catalog

    # Markdown was written and contains both file paths.
    md = (tmp_path / CATALOG_MD).read_text()
    assert "src/lexer.py" in md
    assert "src/parser.py" in md
    assert "stub purpose" in md

    # Python symbols extracted via AST (no LLM needed).
    lexer = next(f for f in catalog.files if f.path == "src/lexer.py")
    assert any(s.name == "tokenize" for s in lexer.public_symbols)


async def test_unchanged_repo_uses_zero_llm_calls(tmp_path: Path):
    """The whole point: re-running the indexer on an unchanged repo must
    not call the LLM. If the cache check works, the second call succeeds
    even without any override (TestModel only used for the first pass)."""
    _init_repo(tmp_path)
    with summarizer_agent.override(model=TestModel(custom_output_text="v1 purpose")):
        first = await index_repo(tmp_path)

    # No override here — if the indexer tries to call Haiku it would either
    # (a) actually hit the API, or (b) fail in CI. The test passes iff every
    # file is cached and the LLM path is skipped entirely.
    second = await index_repo(tmp_path)

    assert {f.path: f.purpose for f in first.files} == {
        f.path: f.purpose for f in second.files
    }
    stats = index_stats(first, second)
    assert stats == {"total": 3, "added": 0, "modified": 0, "unchanged": 3}


async def test_modified_file_triggers_resummary(tmp_path: Path):
    _init_repo(tmp_path)
    with summarizer_agent.override(model=TestModel(custom_output_text="v1 purpose")):
        first = await index_repo(tmp_path)

    # Modify lexer.py. Only that file should be re-summarized.
    (tmp_path / "src" / "lexer.py").write_text(
        '"""Tokenizer module (updated)."""\n\ndef tokenize(s: str) -> list[str]:\n    return list(s)\n'
    )

    with summarizer_agent.override(model=TestModel(custom_output_text="v2 purpose")):
        second = await index_repo(tmp_path)

    by_path = {f.path: f for f in second.files}
    assert by_path["src/lexer.py"].purpose == "v2 purpose"
    assert by_path["src/parser.py"].purpose == "v1 purpose"  # untouched
    assert by_path["README.md"].purpose == "v1 purpose"      # untouched
    assert by_path["src/lexer.py"].content_hash != next(
        f for f in first.files if f.path == "src/lexer.py"
    ).content_hash

    stats = index_stats(first, second)
    assert stats == {"total": 3, "added": 0, "modified": 1, "unchanged": 2}


async def test_refuses_non_git_directory(tmp_path: Path):
    (tmp_path / "x.py").write_text("x = 1\n")
    with pytest.raises(ValueError, match="not a git repository"):
        ensure_git_repo(tmp_path)


async def test_new_file_added_picked_up(tmp_path: Path):
    _init_repo(tmp_path)
    with summarizer_agent.override(model=TestModel(custom_output_text="v1 purpose")):
        await index_repo(tmp_path)

    (tmp_path / "src" / "new_module.py").write_text(
        '"""New module."""\n\ndef hello() -> str:\n    return "hi"\n'
    )

    with summarizer_agent.override(model=TestModel(custom_output_text="newly summarized")):
        second = await index_repo(tmp_path)

    by_path = {f.path: f for f in second.files}
    assert "src/new_module.py" in by_path
    assert by_path["src/new_module.py"].purpose == "newly summarized"
    # Existing files keep their v1 purposes (proves zero LLM call for cached entries).
    assert by_path["src/lexer.py"].purpose == "v1 purpose"
