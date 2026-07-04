"""
Token-bucket rate limiter with Binance weight awareness and 429 backoff.

Binance API has a per-minute weight limit (default 1200).
Different endpoints consume different weights:
  - klines: weight 1 (up to 100 candles) to 10 (over 1000 candles)
  - funding rate: weight 1

When a 429 (rate limit exceeded) response is received, the caller can
call ``handle_error()`` to trigger exponential backoff with jitter.
"""

import random
import time
import threading
from typing import Any, Optional


_Clock = Any  # clock-like: duck-typed with .time() and .sleep()


class BinanceRateLimiter:
    """Token-bucket rate limiter for Binance API weight tracking.

    Usage:
        limiter = BinanceRateLimiter(max_weight_per_minute=1200)
        limiter.acquire(weight=1)   # blocks until a token is available
        limiter.acquire(weight=10)  # blocks longer

    429 backoff:
        try:
            data = client.get_funding_rate(...)
        except BinanceClientError as e:
            limiter.handle_error(e, retry_count=attempt)
            # retry the request
    """

    # Default backoff parameters
    BASE_BACKOFF_SECONDS = 1.0
    MAX_BACKOFF_SECONDS = 60.0
    JITTER_FACTOR = 0.5

    def __init__(
        self,
        max_weight_per_minute: int = 1200,
        clock: Optional[_Clock] = None,
    ) -> None:
        """Initialize rate limiter.

        Args:
            max_weight_per_minute: Maximum total weight per rolling 60s window.
            clock: Optional clock-like object with ``time()`` (default: time).
                   Pass a mock clock for deterministic testing.
        """
        self._max_weight = max_weight_per_minute
        self._clock = clock or time
        self._lock = threading.Lock()
        # Rolling window: list of (timestamp, weight) entries
        self._window: list[tuple[float, int]] = []

    def acquire(self, weight: int = 1) -> None:
        """Block until the requested weight can be accommodated.

        Spins (busy-waits with short sleep) so the calling thread is
        delayed but no event loop is blocked.  This is appropriate for
        synchronous CLI backfill code; for async clients use an async
        variant instead.
        """
        while True:
            with self._lock:
                self._evict_expired()
                current_weight = sum(w for _, w in self._window)
                if current_weight + weight <= self._max_weight:
                    self._window.append((self._clock.time(), weight))
                    return
            # Wait before retrying
            self._clock.sleep(0.05)

    def handle_error(
        self,
        error: Exception,
        retry_count: int = 0,
    ) -> float:
        """Handle an API error, applying exponential backoff for 429s.

        If *error* has a ``status_code`` attribute equal to 429, sleeps
        for ``BASE_BACKOFF_SECONDS * 2 ** retry_count + uniform jitter``
        (capped at ``MAX_BACKOFF_SECONDS``).  For non-429 errors this
        method does nothing and returns 0.0.

        Returns:
            The backoff duration in seconds (0.0 if no backoff was applied).
        """
        status = getattr(error, "status_code", None)
        if status != 429:
            return 0.0

        delay = min(
            self.BASE_BACKOFF_SECONDS * (2 ** retry_count),
            self.MAX_BACKOFF_SECONDS,
        )
        jitter = random.uniform(0, self.JITTER_FACTOR * delay)
        total_delay = delay + jitter
        self._clock.sleep(total_delay)
        return total_delay

    def _evict_expired(self) -> None:
        """Remove entries older than 60 seconds from the rolling window."""
        now = self._clock.time()
        cutoff = now - 60.0
        self._window = [(ts, w) for ts, w in self._window if ts >= cutoff]

    @property
    def current_weight(self) -> int:
        """Total weight used in the current 60-second window."""
        with self._lock:
            self._evict_expired()
            return sum(w for _, w in self._window)

    def reset(self) -> None:
        """Clear the window (for testing or error recovery)."""
        with self._lock:
            self._window.clear()
