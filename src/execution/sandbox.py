"""Sandboxed Python execution.

Two entry points:

- ``run_python(code, test_code)`` — execute a code snippet plus tests in a
  fresh subprocess with CPU / address-space / nproc rlimits and a wall-clock
  timeout. Used by v1's evaluator-optimizer loop tests and ad-hoc snippets.

- ``run_pytest(repo_path, test_target)`` — run ``python -m pytest`` inside a
  target repo with the same limits, used by the Applier after writing changes.

Defenses are layered:

- ``RLIMIT_CPU`` caps CPU seconds (catches busy loops).
- ``RLIMIT_AS`` caps virtual address space (best-effort on macOS, which only
  partially implements it).
- ``RLIMIT_NPROC`` blocks fork bombs (best-effort; per-UID semantics on Linux
  make a hard "==1" limit unrealistic).
- ``asyncio.wait_for`` enforces wall-clock time and kills the process on
  expiry — this catches the cases CPU rlimits don't (sleep, blocking IO).
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

from src.config import SANDBOX_MEM_MB, SANDBOX_TIMEOUT_S
from src.schemas import ErrorCategory, ExecutionResult


# Preamble injected at the top of the user script. It runs in the subprocess
# before any user code, so the limits are in effect for the entire run.
_PREAMBLE_TEMPLATE = """\
import resource as _r
try:
    _r.setrlimit(_r.RLIMIT_CPU, ({cpu_s}, {cpu_s}))
except (OSError, ValueError):
    pass
try:
    _r.setrlimit(_r.RLIMIT_AS, ({mem_b}, {mem_b}))
except (OSError, ValueError):
    pass
try:
    _soft, _hard = _r.getrlimit(_r.RLIMIT_NPROC)
    _r.setrlimit(_r.RLIMIT_NPROC, (max(1, _soft // 2), _hard))
except (OSError, ValueError, AttributeError):
    pass
del _r
"""


# Signals that mean "we ran out of time/CPU." Negative exit_code means the
# process was killed by signal abs(exit_code).
_TIMEOUT_SIGNALS = {9, 24}  # SIGKILL (often from wall-clock kill), SIGXCPU


def _is_timeout(exit_code: int, wall_clock_timed_out: bool) -> bool:
    if wall_clock_timed_out:
        return True
    return exit_code < 0 and -exit_code in _TIMEOUT_SIGNALS


def _classify(exit_code: int, stderr: str, timed_out: bool) -> ErrorCategory:
    if timed_out:
        return "timeout"
    if exit_code == 0:
        return "none"
    if "SyntaxError" in stderr:
        return "syntax"
    if "AssertionError" in stderr:
        return "assertion"
    return "runtime"


async def _spawn(
    argv: list[str],
    cwd: Path | None,
    timeout_s: float,
) -> tuple[int, str, str, int, bool]:
    """Return (exit_code, stdout, stderr, runtime_ms, timed_out)."""
    started = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    timed_out = False
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_s
        )
    except asyncio.TimeoutError:
        timed_out = True
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=2)
        except asyncio.TimeoutError:
            stdout_b, stderr_b = b"", b""

    runtime_ms = int((time.perf_counter() - started) * 1000)
    exit_code = proc.returncode if proc.returncode is not None else -1
    return (
        exit_code,
        stdout_b.decode("utf-8", errors="replace"),
        stderr_b.decode("utf-8", errors="replace"),
        runtime_ms,
        timed_out,
    )


async def run_python(
    code: str,
    test_code: str = "",
    timeout_s: int = SANDBOX_TIMEOUT_S,
    mem_mb: int = SANDBOX_MEM_MB,
) -> ExecutionResult:
    """Run ``code`` (and any ``test_code``) inside a sandboxed subprocess."""
    preamble = _PREAMBLE_TEMPLATE.format(
        cpu_s=timeout_s,
        mem_b=mem_mb * 1024 * 1024,
    )
    script = f"{preamble}\n{code}\n{test_code}\n"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(script)
        script_path = Path(f.name)

    try:
        exit_code, stdout, stderr, runtime_ms, wall_timed_out = await _spawn(
            [sys.executable, str(script_path)],
            cwd=None,
            timeout_s=timeout_s + 2,
        )
    finally:
        script_path.unlink(missing_ok=True)

    timed_out = _is_timeout(exit_code, wall_timed_out)
    return ExecutionResult(
        success=exit_code == 0 and not timed_out,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        runtime_ms=runtime_ms,
        timed_out=timed_out,
        error_category=_classify(exit_code, stderr, timed_out),
    )


async def run_pytest(
    repo_path: Path,
    test_target: str | None = None,
    timeout_s: int = SANDBOX_TIMEOUT_S * 6,
) -> ExecutionResult:
    """Run ``pytest`` inside ``repo_path``.

    ``test_target`` may be a file path or a pytest node id; omit to run the
    whole suite. Uses the current interpreter; the caller must ensure pytest
    and the repo's deps are importable in this environment (a typical setup
    is to spawn this from the repo's own venv).
    """
    argv = [sys.executable, "-m", "pytest", "-q", "--tb=short"]
    if test_target:
        argv.append(test_target)

    exit_code, stdout, stderr, runtime_ms, wall_timed_out = await _spawn(
        argv,
        cwd=repo_path,
        timeout_s=timeout_s,
    )

    timed_out = _is_timeout(exit_code, wall_timed_out)
    # pytest writes failure tracebacks to stdout, not stderr; merge for
    # classification but keep them separate in the result.
    combined = stderr + "\n" + stdout
    return ExecutionResult(
        success=exit_code == 0 and not timed_out,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        runtime_ms=runtime_ms,
        timed_out=timed_out,
        error_category=_classify(exit_code, combined, timed_out),
    )
