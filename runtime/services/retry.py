"""Generic retry utility with exponential backoff and jitter.

Provides:
- retry_with_backoff: synchronous retry
- async_retry_with_backoff: asynchronous retry
- is_retryable_error: exception type checking
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


def is_retryable_error(
    exception: Exception,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> bool:
    """Check whether *exception* is an instance of any retryable type."""
    return isinstance(exception, retryable_exceptions)


def _compute_delay(
    attempt: int,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
) -> float:
    """Compute the delay before the given *attempt* (0-based)."""
    delay = base_delay * (backoff_factor ** attempt)
    delay = min(delay, max_delay)
    delay += random.uniform(0, 0.1)  # jitter 0-100ms
    return delay


def retry_with_backoff(
    fn: Callable[..., T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    logger: logging.Logger | None = None,
) -> T:
    """Retry a synchronous function with exponential backoff and jitter.

    Args:
        fn: The function to retry.
        max_retries: Maximum number of retry attempts (default 3).
        base_delay: Base delay in seconds (default 1.0).
        backoff_factor: Multiplier for each retry (default 2.0).
        max_delay: Maximum delay cap in seconds (default 60.0).
        retryable_exceptions: Exception types that trigger a retry.
        logger: Optional logger for retry logging.

    Returns:
        The return value of fn.

    Raises:
        The last exception raised by fn if all retries are exhausted.
    """
    log = logger or logging.getLogger(__name__)
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return fn()
        except retryable_exceptions as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = _compute_delay(attempt, base_delay, backoff_factor, max_delay)
                log.warning(
                    "retry attempt=%d/%d error=%s: %s next_delay=%.2fs",
                    attempt + 1, max_retries,
                    type(exc).__name__, exc, delay,
                )
                time.sleep(delay)
            else:
                log.error(
                    "retry exhausted attempt=%d/%d error=%s: %s",
                    attempt + 1, max_retries,
                    type(exc).__name__, exc,
                )
        except Exception as exc:
            # Non-retryable — raise immediately
            raise exc

    raise last_exc  # type: ignore[misc]


async def async_retry_with_backoff(
    fn: Callable[..., Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    logger: logging.Logger | None = None,
) -> T:
    """Retry an async function with exponential backoff and jitter.

    Same semantics as :func:`retry_with_backoff` but for async callables.
    """
    log = logger or logging.getLogger(__name__)
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except retryable_exceptions as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = _compute_delay(attempt, base_delay, backoff_factor, max_delay)
                log.warning(
                    "async retry attempt=%d/%d error=%s: %s next_delay=%.2fs",
                    attempt + 1, max_retries,
                    type(exc).__name__, exc, delay,
                )
                await asyncio.sleep(delay)
            else:
                log.error(
                    "async retry exhausted attempt=%d/%d error=%s: %s",
                    attempt + 1, max_retries,
                    type(exc).__name__, exc,
                )
        except Exception as exc:
            raise exc

    raise last_exc  # type: ignore[misc]
