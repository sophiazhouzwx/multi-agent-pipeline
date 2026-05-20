"""Git-aware applier with sandbox tests + automatic rollback.

Workflow:
1. Verify the target is a clean git repo (refuse on dirty working tree).
2. Remember the original branch for safe return on rollback.
3. Create + check out a new working branch `agent/<slug>`.
4. Write each FileEdit to disk (create parent dirs as needed).
5. Stage and commit the changes.
6. Run the repo's tests in the sandbox.
7. On test failure: hard-reset, switch back to the original branch, delete
   the working branch entirely. The repo is bit-for-bit identical to its
   pre-Applier state.
8. On test success: stay on the working branch with the commit. Return the
   commit sha so the orchestrator can persist it.

The test runner is injected so tests can replace it with a fake; the default
is ``src.execution.sandbox.run_pytest``.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

from git import GitCommandError, InvalidGitRepositoryError
from git import Repo as GitRepo

from src.execution.sandbox import run_pytest
from src.schemas import ApplyResult, ChangeProposal, ExecutionResult


# pytest exit codes we treat as "tests passed (or no tests to break)".
# 0  = all tests passed
# 5  = no tests collected — the change didn't break what doesn't exist
_TEST_PASS_CODES: frozenset[int] = frozenset({0, 5})

TestFn = Callable[[Path], Awaitable[ExecutionResult]]


def make_branch_slug(request: str, max_len: int = 40) -> str:
    """Generate a branch name like ``agent/add-json-flag-20260519-160355``.

    Slug is the request lowercased with non-alphanumeric chars collapsed to
    hyphens, trimmed to ``max_len``, with a UTC timestamp appended so two
    runs of the same request produce distinct branches.
    """
    base = re.sub(r"[^a-z0-9]+", "-", request.lower()).strip("-")
    base = base[:max_len].strip("-")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"agent/{base}-{ts}" if base else f"agent/run-{ts}"


def _ensure_clean_repo(repo_path: Path) -> GitRepo:
    """Open repo_path as a git repo; refuse if anything is dirty or staged."""
    try:
        repo = GitRepo(repo_path)
    except InvalidGitRepositoryError as exc:
        raise ValueError(f"{repo_path} is not a git repository") from exc
    if repo.is_dirty(untracked_files=True):
        raise ValueError(
            f"{repo_path} has uncommitted or untracked changes. Commit, stash, "
            "or clean them before running the Applier."
        )
    return repo


def _write_edits(repo_path: Path, proposal: ChangeProposal) -> None:
    """Write each FileEdit's new_content to its target path."""
    for edit in proposal.edits:
        target = repo_path / edit.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(edit.new_content, encoding="utf-8")


async def apply_changes(
    repo_path: Path,
    proposal: ChangeProposal,
    request_summary: str,
    test_fn: TestFn = run_pytest,
) -> ApplyResult:
    """Apply ``proposal`` on a new branch, run tests, commit or rollback."""
    repo_path = repo_path.resolve()
    repo = _ensure_clean_repo(repo_path)

    original_branch: str
    try:
        original_branch = repo.active_branch.name
    except TypeError:
        # Detached HEAD — branch slug must be created from current commit.
        original_branch = repo.head.commit.hexsha

    branch_name = make_branch_slug(request_summary)

    # Create & switch to the working branch.
    new_branch = repo.create_head(branch_name)
    new_branch.checkout()

    try:
        _write_edits(repo_path, proposal)
        repo.git.add(A=True)
        commit_message = f"agent: {request_summary}".strip()
        commit = repo.index.commit(commit_message)
        commit_sha = commit.hexsha
    except Exception as exc:
        # Something went wrong before tests even ran — clean up.
        repo.git.checkout(original_branch)
        try:
            repo.delete_head(branch_name, force=True)
        except GitCommandError:
            pass
        return ApplyResult(
            branch_name=branch_name,
            applied_commit=None,
            test_result=None,
            rolled_back=True,
            rollback_reason=f"write/commit failed before tests: {exc}",
        )

    # Run tests in the sandbox.
    try:
        test_result = await test_fn(repo_path)
    except Exception as exc:
        test_result = ExecutionResult(
            success=False,
            stdout="",
            stderr=str(exc),
            exit_code=-1,
            runtime_ms=0,
            timed_out=False,
            error_category="runtime",
        )

    passed = (
        test_result is not None
        and test_result.exit_code in _TEST_PASS_CODES
        and not test_result.timed_out
    )

    if not passed:
        # Roll back: hard-reset, switch back, delete the branch.
        try:
            repo.git.reset("--hard", "HEAD~1")
        except GitCommandError:
            # Possible if there were no prior commits; ignore.
            pass
        try:
            repo.git.checkout(original_branch)
        except GitCommandError:
            pass
        try:
            repo.delete_head(branch_name, force=True)
        except GitCommandError:
            pass
        return ApplyResult(
            branch_name=branch_name,
            applied_commit=None,
            test_result=test_result,
            rolled_back=True,
            rollback_reason=(
                f"tests failed (exit={test_result.exit_code}, "
                f"timed_out={test_result.timed_out})"
            ),
        )

    return ApplyResult(
        branch_name=branch_name,
        applied_commit=commit_sha,
        test_result=test_result,
        rolled_back=False,
        rollback_reason="",
    )
