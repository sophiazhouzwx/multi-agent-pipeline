"""Tests for the retry-with-backoff helper."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelHTTPError

from src._retry import RETRYABLE_STATUSES, run_with_retry


def _http_error(status: int) -> ModelHTTPError:
    return ModelHTTPError(status_code=status, model_name="test", body={})


@pytest.mark.asyncio
async def test_succeeds_first_try():
    calls = 0

    async def ok():
        nonlocal calls
        calls += 1
        return "result"

    out = await run_with_retry(ok, label="t", max_attempts=3, base_delay_s=0.01)
    assert out == "result"
    assert calls == 1


@pytest.mark.asyncio
async def test_retries_429_then_succeeds():
    calls = 0

    async def flaky():
        nonlocal calls
        calls += 1
        if calls < 2:
            raise _http_error(429)
        return "result"

    out = await run_with_retry(flaky, label="t", max_attempts=4, base_delay_s=0.01)
    assert out == "result"
    assert calls == 2


@pytest.mark.asyncio
async def test_retries_then_gives_up_and_raises():
    calls = 0

    async def always_fails():
        nonlocal calls
        calls += 1
        raise _http_error(429)

    with pytest.raises(ModelHTTPError):
        await run_with_retry(always_fails, label="t", max_attempts=3, base_delay_s=0.01)
    assert calls == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_does_not_retry_400_class_errors():
    """4xx errors other than 429 should fail fast — they're our bugs, not transient."""
    calls = 0

    async def bad_request():
        nonlocal calls
        calls += 1
        raise _http_error(400)

    with pytest.raises(ModelHTTPError):
        await run_with_retry(bad_request, label="t", max_attempts=5, base_delay_s=0.01)
    assert calls == 1


@pytest.mark.asyncio
async def test_retries_5xx_errors():
    for status in (500, 502, 503, 504):
        calls = 0

        async def flaky():
            nonlocal calls
            calls += 1
            if calls < 2:
                raise _http_error(status)
            return f"ok-{status}"

        out = await run_with_retry(flaky, label="t", max_attempts=3, base_delay_s=0.01)
        assert out == f"ok-{status}"
        assert calls == 2


def test_retryable_statuses_membership():
    assert 429 in RETRYABLE_STATUSES
    assert 500 in RETRYABLE_STATUSES
    assert 503 in RETRYABLE_STATUSES
    assert 400 not in RETRYABLE_STATUSES
    assert 401 not in RETRYABLE_STATUSES
    assert 404 not in RETRYABLE_STATUSES
