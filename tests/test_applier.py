"""Hermetic tests for the git-aware applier.

Uses real git repos in tmp_path + an injected fake test runner so we never
spawn pytest subprocesses (fast and deterministic).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from git import Repo as GitRepo

from src.apply.applier import (
    _TEST_PASS_CODES,
    _write_edits,
    apply_changes,
    make_branch_slug,
)
from src.schemas import ChangePlan, ChangeProposal, ExecutionResult, FileEdit


def _init_repo(root: Path) -> GitRepo:
    repo = GitRepo.init(root)
    # gitpython needs a configured identity to commit in CI environments.
    with repo.config_writer() as cw:
        cw.set_value("user", "email", "test@local")
        cw.set_value("user", "name", "test")
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("def f():\n    return 1\n")
    (root / "README.md").write_text("# example\n")
    repo.git.add(A=True)
    repo.index.commit("initial")
    return repo


def _proposal(path: str = "src/main.py", new_content: str = "def f():\n    return 42\n") -> ChangeProposal:
    return ChangeProposal(
        plan=ChangePlan(
            summary="Change f to return 42",
            affected_files=[path],
            steps=["replace return value"],
        ),
        edits=[FileEdit(path=path, new_content=new_content, rationale="changed return")],
    )


async def _fake_pass(repo_path: Path) -> ExecutionResult:
    return ExecutionResult(
        success=True,
        stdout="1 passed",
        stderr="",
        exit_code=0,
        runtime_ms=10,
        timed_out=False,
        error_category="none",
    )


async def _fake_no_tests(repo_path: Path) -> ExecutionResult:
    return ExecutionResult(
        success=False,
        stdout="no tests ran",
        stderr="",
        exit_code=5,
        runtime_ms=5,
        timed_out=False,
        error_category="none",
    )


async def _fake_fail(repo_path: Path) -> ExecutionResult:
    return ExecutionResult(
        success=False,
        stdout="1 failed",
        stderr="AssertionError: nope",
        exit_code=1,
        runtime_ms=15,
        timed_out=False,
        error_category="assertion",
    )


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------
def test_slug_alphanumeric_only(monkeypatch):
    # No need to freeze time — we just check the structure.
    slug = make_branch_slug("Add --json flag to ASK command!")
    assert slug.startswith("agent/add-json-flag-to-ask-command-")
    # Final segment is a 15-char ISO-like timestamp YYYYMMDD-HHMMSS.
    assert len(slug.split("-")[-2]) == 8  # YYYYMMDD
    assert len(slug.split("-")[-1]) == 6  # HHMMSS


def test_slug_empty_request():
    slug = make_branch_slug("")
    assert slug.startswith("agent/run-")


def test_slug_max_len_respected():
    very_long = "a" * 200
    slug = make_branch_slug(very_long, max_len=30)
    # 30 'a's + dashes + timestamp. Body before timestamp shouldn't exceed 30.
    body = slug[len("agent/") :].rsplit("-", 2)[0]
    assert len(body) <= 30


# ---------------------------------------------------------------------------
# write_edits helper
# ---------------------------------------------------------------------------
def test_write_edits_creates_parent_dirs(tmp_path: Path):
    proposal = ChangeProposal(
        plan=ChangePlan(
            summary="add nested",
            affected_files=["new/nested/dir/file.py"],
            steps=["create file"],
        ),
        edits=[
            FileEdit(
                path="new/nested/dir/file.py",
                new_content="x = 1\n",
                rationale="new",
            )
        ],
    )
    _write_edits(tmp_path, proposal)
    assert (tmp_path / "new" / "nested" / "dir" / "file.py").read_text() == "x = 1\n"


# ---------------------------------------------------------------------------
# Apply: happy path
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_apply_happy_path(tmp_path: Path):
    repo = _init_repo(tmp_path)
    head_before = repo.head.commit.hexsha

    result = await apply_changes(
        tmp_path,
        _proposal(),
        "change f to return 42",
        test_fn=_fake_pass,
    )

    assert not result.rolled_back
    assert result.applied_commit is not None
    assert result.applied_commit != head_before
    # Branch was created and we're on it.
    assert repo.active_branch.name == result.branch_name
    # File was actually written.
    assert (tmp_path / "src" / "main.py").read_text() == "def f():\n    return 42\n"


@pytest.mark.asyncio
async def test_apply_treats_no_tests_as_pass(tmp_path: Path):
    """pytest exit code 5 means no tests collected — treat as pass."""
    _init_repo(tmp_path)
    result = await apply_changes(
        tmp_path,
        _proposal(),
        "trivial",
        test_fn=_fake_no_tests,
    )
    assert not result.rolled_back
    assert result.applied_commit is not None


# ---------------------------------------------------------------------------
# Apply: rollback paths
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_apply_rolls_back_on_test_failure(tmp_path: Path):
    repo = _init_repo(tmp_path)
    head_before = repo.head.commit.hexsha
    main_content_before = (tmp_path / "src" / "main.py").read_text()

    result = await apply_changes(
        tmp_path,
        _proposal(),
        "doomed change",
        test_fn=_fake_fail,
    )

    assert result.rolled_back
    assert result.applied_commit is None
    assert "tests failed" in result.rollback_reason
    # We're back on the original branch.
    assert repo.active_branch.name in {"main", "master"}
    # HEAD is exactly where we started.
    assert repo.head.commit.hexsha == head_before
    # File content is restored.
    assert (tmp_path / "src" / "main.py").read_text() == main_content_before
    # The agent branch was deleted.
    branch_names = {h.name for h in repo.heads}
    assert result.branch_name not in branch_names


@pytest.mark.asyncio
async def test_apply_refuses_dirty_repo(tmp_path: Path):
    _init_repo(tmp_path)
    # Add an uncommitted change.
    (tmp_path / "src" / "main.py").write_text("def f():\n    return 999\n")

    with pytest.raises(ValueError, match="uncommitted"):
        await apply_changes(
            tmp_path,
            _proposal(),
            "should not apply",
            test_fn=_fake_pass,
        )


@pytest.mark.asyncio
async def test_apply_refuses_non_git_dir(tmp_path: Path):
    (tmp_path / "f.py").write_text("x = 1\n")
    with pytest.raises(ValueError, match="not a git repository"):
        await apply_changes(
            tmp_path,
            _proposal("f.py"),
            "irrelevant",
            test_fn=_fake_pass,
        )


# ---------------------------------------------------------------------------
# Pass codes constant
# ---------------------------------------------------------------------------
def test_test_pass_codes():
    assert 0 in _TEST_PASS_CODES
    assert 5 in _TEST_PASS_CODES  # no tests collected
    assert 1 not in _TEST_PASS_CODES  # real failure
