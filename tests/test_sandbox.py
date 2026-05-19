"""Hermetic tests for the sandboxed Python executor (no API calls)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src.execution.sandbox import run_pytest, run_python


pytestmark = pytest.mark.asyncio


async def test_happy_path():
    result = await run_python(
        code="def add(a, b):\n    return a + b\n",
        test_code="assert add(2, 3) == 5\n",
    )
    assert result.success
    assert result.exit_code == 0
    assert not result.timed_out
    assert result.error_category == "none"


async def test_assertion_failure_classified():
    result = await run_python(
        code="def add(a, b):\n    return a + b\n",
        test_code="assert add(2, 3) == 6, 'expected 6'\n",
    )
    assert not result.success
    assert result.error_category == "assertion"
    assert "AssertionError" in result.stderr


async def test_syntax_error_classified():
    result = await run_python(code="def broken(:\n    pass\n")
    assert not result.success
    assert result.error_category == "syntax"
    assert "SyntaxError" in result.stderr


async def test_runtime_error_classified():
    result = await run_python(code="raise ValueError('boom')\n")
    assert not result.success
    assert result.error_category == "runtime"
    assert "ValueError" in result.stderr


async def test_wall_clock_timeout():
    result = await run_python(
        code="while True:\n    pass\n",
        timeout_s=2,
    )
    assert not result.success
    assert result.timed_out
    assert result.error_category == "timeout"
    # Wall-clock guard fires no later than timeout_s + 2.
    assert result.runtime_ms < 6000


async def test_stdout_captured():
    result = await run_python(code="print('hello sandbox')\n")
    assert result.success
    assert "hello sandbox" in result.stdout


async def test_run_pytest_against_self(tmp_path: Path):
    """Smoke test for run_pytest: create a tiny inline test and run it."""
    test_file = tmp_path / "test_tiny.py"
    test_file.write_text("def test_truth():\n    assert 1 + 1 == 2\n")

    # Need a minimal conftest to make pytest treat tmp_path as the rootdir
    # without pulling in the project's pyproject.toml settings.
    (tmp_path / "conftest.py").write_text("")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\nasyncio_mode = 'strict'\n"
    )

    result = await run_pytest(tmp_path, test_target="test_tiny.py", timeout_s=30)
    assert result.success, f"pytest failed unexpectedly: {result.stderr}\n{result.stdout}"
    assert result.exit_code == 0


async def test_run_pytest_failure_propagates(tmp_path: Path):
    test_file = tmp_path / "test_broken.py"
    test_file.write_text("def test_lies():\n    assert 1 == 2\n")
    (tmp_path / "conftest.py").write_text("")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\nasyncio_mode = 'strict'\n"
    )

    result = await run_pytest(tmp_path, test_target="test_broken.py", timeout_s=30)
    assert not result.success
    assert result.exit_code != 0
    assert "assert 1 == 2" in result.stdout or "AssertionError" in result.stdout
