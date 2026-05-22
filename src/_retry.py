"""Retry helper for transient LLM-call failures (429 + 5xx).

Wraps any ``await agent.run(...)`` call so callers don't have to reason about
when the proxy is throttling vs genuinely failing. Uses exponential backoff;
prints a short notice to stderr on each retry so long waits aren't silent.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Awaitable, Callable, TypeVar

from pydantic_ai.exceptions import ModelHTTPError

T = TypeVar("T")


# HTTP statuses that are worth retrying. 429 = rate limit (Vertex AI quota
# bursts behind the CVS proxy are the usual culprit). 5xx = transient server.
RETRYABLE_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})

DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BASE_DELAY_S = 4.0


async def run_with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    label: str = "",
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay_s: float = DEFAULT_BASE_DELAY_S,
) -> T:
    """Call ``fn`` with exponential backoff on retryable HTTP errors.

    Delays: ``base_delay_s * 2**attempt`` seconds. With the defaults the
    schedule is 4s, 8s, 16s (3 retries on top of the first try = 4 attempts
    total, max wait ~28s).
    """
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return await fn()
        except ModelHTTPError as e:
            last_exc = e
            if e.status_code not in RETRYABLE_STATUSES or attempt == max_attempts - 1:
                raise
            delay = base_delay_s * (2 ** attempt)
            print(
                f"[retry] {label or 'llm call'}: HTTP {e.status_code}, waiting "
                f"{delay:.0f}s (attempt {attempt + 1}/{max_attempts})",
                file=sys.stderr,
                flush=True,
            )
            await asyncio.sleep(delay)
    # Unreachable: the loop either returns or raises. Re-raise for the
    # type checker.
    assert last_exc is not None
    raise last_exc
