"""Tests for the generic retry utility."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock, patch

import pytest

from runtime.services.retry import async_retry_with_backoff, retry_with_backoff


class _RetryableError(Exception):
    pass


class _NonRetryableError(Exception):
    pass


def test_retry_success_first_try() -> None:
    fn = MagicMock(return_value=42)
    result = retry_with_backoff(fn, max_retries=3)
    assert result == 42
    assert fn.call_count == 1


def test_retry_success_after_retries() -> None:
    call_count = 0

    def flaky() -> int:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise _RetryableError("not yet")
        return 99

    result = retry_with_backoff(
        flaky, max_retries=5, base_delay=0.01, retryable_exceptions=(_RetryableError,),
    )
    assert result == 99
    assert call_count == 3


def test_retry_exhaustion() -> None:
    fn = MagicMock(side_effect=_RetryableError("always fails"))
    with pytest.raises(_RetryableError, match="always fails"):
        retry_with_backoff(
            fn, max_retries=2, base_delay=0.01, retryable_exceptions=(_RetryableError,),
        )
    assert fn.call_count == 3  # initial + 2 retries


def test_retry_non_retryable_exception() -> None:
    fn = MagicMock(side_effect=_NonRetryableError("bad"))
    with pytest.raises(_NonRetryableError):
        retry_with_backoff(
            fn, max_retries=3, base_delay=0.01, retryable_exceptions=(_RetryableError,),
        )
    assert fn.call_count == 1


def test_retry_backoff_delay_increases() -> None:
    delays: list[float] = []

    def flaky() -> None:
        raise _RetryableError("nope")

    original_sleep = _monkey_sleep = None

    def tracking_sleep(delay: float) -> None:
        delays.append(delay)

    with patch("runtime.services.retry.time.sleep", side_effect=tracking_sleep):
        with pytest.raises(_RetryableError):
            retry_with_backoff(
                flaky, max_retries=2, base_delay=1.0, backoff_factor=2.0,
                max_delay=60.0, retryable_exceptions=(_RetryableError,),
            )

    # Should have 2 delays (attempt 0 and attempt 1) before final failure
    assert len(delays) == 2
    # attempt 0: 1.0 + jitter ≈ 1.0-1.1, attempt 1: 2.0 + jitter ≈ 2.0-2.1
    assert delays[0] < delays[1]
    assert 1.0 <= delays[0] <= 1.2
    assert 2.0 <= delays[1] <= 2.2


def test_retry_max_delay_cap() -> None:
    delays: list[float] = []

    def flaky() -> None:
        raise _RetryableError("nope")

    def tracking_sleep(delay: float) -> None:
        delays.append(delay)

    with patch("runtime.services.retry.time.sleep", side_effect=tracking_sleep):
        with pytest.raises(_RetryableError):
            retry_with_backoff(
                flaky, max_retries=5, base_delay=1.0, backoff_factor=10.0,
                max_delay=5.0, retryable_exceptions=(_RetryableError,),
            )

    # All delays should be capped at ~5.0s (+ jitter)
    for d in delays:
        assert d <= 5.2


def test_retry_logging() -> None:
    logger = MagicMock(spec=logging.Logger)
    fn = MagicMock(side_effect=_RetryableError("log me"))

    with patch("runtime.services.retry.time.sleep"):
        with pytest.raises(_RetryableError):
            retry_with_backoff(
                fn, max_retries=2, base_delay=0.01,
                retryable_exceptions=(_RetryableError,),
                logger=logger,
            )

    # Should log warning on each retry, error on exhaustion
    warning_calls = [c for c in logger.warning.call_args_list if "retry attempt" in str(c)]
    error_calls = [c for c in logger.error.call_args_list if "retry exhausted" in str(c)]
    assert len(warning_calls) == 2  # 2 retries
    assert len(error_calls) == 1  # exhaustion


@pytest.mark.asyncio
async def test_async_retry_success_first_try() -> None:
    fn = MagicMock(return_value=asyncio.sleep(0, result="ok"))
    result = await async_retry_with_backoff(fn, max_retries=3)
    assert result == "ok"


@pytest.mark.asyncio
async def test_async_retry_exhaustion() -> None:
    async def always_fail() -> str:
        raise _RetryableError("async fail")

    with pytest.raises(_RetryableError, match="async fail"):
        await async_retry_with_backoff(
            always_fail, max_retries=2, base_delay=0.01,
            retryable_exceptions=(_RetryableError,),
        )
