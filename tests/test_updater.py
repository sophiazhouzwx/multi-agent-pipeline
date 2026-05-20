"""Hermetic tests for the catalog updater.

Builds an initial catalog with stub Haiku output, then modifies a file and
confirms that the refresh re-summarizes only that file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from git import Repo as GitRepo
from pydantic_ai.models.test import TestModel

from src.catalog.summarizer import summarizer_agent
from src.catalog.updater import refresh_catalog_after_apply

pytestmark = pytest.mark.asyncio


def _init_repo(root: Path) -> None:
    GitRepo.init(root)
    repo = GitRepo(root)
    with repo.config_writer() as cw:
        cw.set_value("user", "email", "test@local")
        cw.set_value("user", "name", "test")
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text('"""A module."""\n\ndef a() -> int:\n    return 1\n')
    (root / "src" / "b.py").write_text('"""B module."""\n\ndef b() -> int:\n    return 2\n')
    (root / "README.md").write_text("# example\n")
    repo.git.add(A=True)
    repo.index.commit("initial")


async def test_refresh_resummarizes_only_changed_files(tmp_path: Path):
    _init_repo(tmp_path)

    # Initial index — every file gets purpose 'v1'.
    with summarizer_agent.override(model=TestModel(custom_output_text="v1")):
        first = await refresh_catalog_after_apply(tmp_path)

    assert first.files_added == 3
    assert first.files_resummarized == 0
    assert first.files_unchanged == 0
    assert first.files_total == 3
    assert all(f.purpose == "v1" for f in first.catalog.files)

    # Modify exactly one file.
    (tmp_path / "src" / "a.py").write_text('"""A module updated."""\n\ndef a() -> int:\n    return 99\n')

    # Refresh — only the modified file should be re-summarized.
    with summarizer_agent.override(model=TestModel(custom_output_text="v2")):
        second = await refresh_catalog_after_apply(tmp_path)

    assert second.files_total == 3
    assert second.files_added == 0
    assert second.files_resummarized == 1
    assert second.files_unchanged == 2

    by_path = {f.path: f for f in second.catalog.files}
    assert by_path["src/a.py"].purpose == "v2"      # re-summarized
    assert by_path["src/b.py"].purpose == "v1"      # cached
    assert by_path["README.md"].purpose == "v1"     # cached


async def test_refresh_unchanged_repo_uses_no_llm(tmp_path: Path):
    """A refresh on an unchanged repo must not call the summarizer.

    We prove this by NOT overriding the model on the second call — if the
    indexer tried to call Haiku without API credentials in this test env,
    it would fail.
    """
    _init_repo(tmp_path)
    with summarizer_agent.override(model=TestModel(custom_output_text="v1")):
        await refresh_catalog_after_apply(tmp_path)

    # No override here — proves the cache hit path skips the LLM entirely.
    second = await refresh_catalog_after_apply(tmp_path)
    assert second.files_resummarized == 0
    assert second.files_added == 0
    assert second.files_unchanged == 3
