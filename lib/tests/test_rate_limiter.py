"""
Tests for lib/market_data/binance/rate_limiter.py

Uses a mock clock for deterministic timing.
"""

import time
from unittest.mock import Mock, patch

import pytest

from lib.market_data.binance.rate_limiter import BinanceRateLimiter


class MockClock:
    """Deterministic mock clock for rate limiter testing."""

    def __init__(self, start_time: float = 1000.0) -> None:
        self._now = start_time

    def time(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        # Advance clock by the requested sleep duration
        self._now += seconds

    def advance(self, seconds: float) -> None:
        self._now += seconds


class TestBinanceRateLimiter:
    def test_acquire_within_limit(self):
        clock = MockClock()
        limiter = BinanceRateLimiter(max_weight_per_minute=1200, clock=clock)
        # Should not block
        limiter.acquire(weight=1)
        assert limiter.current_weight == 1

    def test_acquire_multiple_within_limit(self):
        clock = MockClock()
        limiter = BinanceRateLimiter(max_weight_per_minute=1200, clock=clock)
        limiter.acquire(weight=500)
        limiter.acquire(weight=500)
        assert limiter.current_weight == 1000

    def test_acquire_blocks_then_succeeds_after_window_expiry(self):
        """When over the limit, acquire blocks until window expires."""
        clock = MockClock()
        limiter = BinanceRateLimiter(max_weight_per_minute=100, clock=clock)
        limiter.acquire(weight=80)          # t=1000, weight=80
        assert limiter.current_weight == 80

        # acquire(30) will block (80+30=110 > 100).
        # The spin loop advances the clock by 0.05s per iteration.
        # After ~60s of spinning the first entry expires
        # and the acquire succeeds with weight=30.
        limiter.acquire(weight=30)

        # The original (1000,80) entry has expired due to clock advancement
        # during the spin loop. Only the new entry remains.
        assert limiter.current_weight == 30

    def test_window_expiry(self):
        clock = MockClock()
        limiter = BinanceRateLimiter(max_weight_per_minute=100, clock=clock)
        limiter.acquire(weight=100)
        assert limiter.current_weight == 100

        # Weight should still be 100 after 30 seconds
        clock.advance(30)
        assert limiter.current_weight == 100

        # After 61 seconds, weight should be 0 (window expired)
        clock.advance(31)
        assert limiter.current_weight == 0

    def test_multiple_entries_evict_oldest(self):
        clock = MockClock()
        limiter = BinanceRateLimiter(max_weight_per_minute=200, clock=clock)
        limiter.acquire(weight=100)  # t=1000
        clock.advance(30)
        limiter.acquire(weight=100)  # t=1030
        assert limiter.current_weight == 200

        # Advance past the first entry (t=1061, 61s after first entry)
        clock.advance(31)
        assert limiter.current_weight == 100  # only the second entry remains

    def test_reset_clears_window(self):
        clock = MockClock()
        limiter = BinanceRateLimiter(max_weight_per_minute=100, clock=clock)
        limiter.acquire(weight=80)
        assert limiter.current_weight == 80
        limiter.reset()
        assert limiter.current_weight == 0

    def test_default_max_weight(self):
        clock = MockClock()
        limiter = BinanceRateLimiter(clock=clock)
        assert limiter._max_weight == 1200

    def test_acquire_with_zero_weight(self):
        clock = MockClock()
        limiter = BinanceRateLimiter(clock=clock)
        limiter.acquire(weight=0)
        assert limiter.current_weight == 0

    def test_current_weight_multiple_intervals(self):
        """Test that current_weight reflects rolling window correctly."""
        clock = MockClock()
        limiter = BinanceRateLimiter(max_weight_per_minute=100, clock=clock)

        limiter.acquire(weight=30)  # t=1000
        clock.advance(10)           # t=1010
        limiter.acquire(weight=40)  # t=1010
        assert limiter.current_weight == 70

        clock.advance(50)           # t=1060, first entry (1000) is still within 60s
        assert limiter.current_weight == 70

        clock.advance(1)            # t=1061, first entry (1000) is now >60s old
        assert limiter.current_weight == 40  # only the second entry remains

    # ------------------------------------------------------------------
    # 429 / Retry / Backoff tests
    # ------------------------------------------------------------------

    def test_handle_error_non_429_does_not_backoff(self):
        """handle_error returns 0.0 for non-429 errors."""
        clock = MockClock()
        limiter = BinanceRateLimiter(clock=clock)
        err = Exception("generic error")
        assert limiter.handle_error(err) == 0.0
        # Clock should not have advanced
        assert clock.time() == 1000.0

    def test_handle_error_429_exponential_backoff(self):
        """handle_error with 429 triggers exponential backoff with jitter."""
        clock = MockClock()
        limiter = BinanceRateLimiter(clock=clock)

        # Mock random.uniform to return 0 for deterministic testing
        with patch("random.uniform", return_value=0.0):
            err = Exception("rate limited")
            err.status_code = 429

            # retry_count=0 => base backoff = 1.0s
            limiter.handle_error(err, retry_count=0)
            assert clock.time() == 1000.0 + 1.0

            # retry_count=1 => 2.0s
            limiter.handle_error(err, retry_count=1)
            assert clock.time() == 1000.0 + 1.0 + 2.0

            # retry_count=2 => 4.0s
            limiter.handle_error(err, retry_count=2)
            assert clock.time() == 1000.0 + 1.0 + 2.0 + 4.0

    def test_handle_error_429_max_backoff_capped(self):
        """Backoff is capped at MAX_BACKOFF_SECONDS."""
        clock = MockClock()
        limiter = BinanceRateLimiter(clock=clock)

        with patch("random.uniform", return_value=0.0):
            err = Exception("rate limited")
            err.status_code = 429

            # retry_count=10 => 2^10 = 1024s, capped at 60s
            limiter.handle_error(err, retry_count=10)
            assert clock.time() == 1000.0 + 60.0

    def test_handle_error_429_with_jitter(self):
        """Jitter is applied to the backoff delay."""
        clock = MockClock()
        limiter = BinanceRateLimiter(clock=clock)

        err = Exception("rate limited")
        err.status_code = 429

        # random.uniform(0, 0.5 * 1.0) = random(0, 0.5)
        # With jitter=0.25, total = 1.0 + 0.25 = 1.25
        with patch("random.uniform", return_value=0.25):
            result = limiter.handle_error(err, retry_count=0)
            assert result == 1.25
            assert clock.time() == 1000.0 + 1.25

    def test_handle_error_returns_backoff_duration(self):
        """handle_error returns the actual backoff duration."""
        clock = MockClock()
        limiter = BinanceRateLimiter(clock=clock)

        with patch("random.uniform", return_value=0.0):
            err = Exception("rate limited")
            err.status_code = 429

            result = limiter.handle_error(err, retry_count=0)
            assert result == 1.0

    def test_handle_error_with_binance_client_error(self):
        """handle_error works with BinanceClientError that has status_code."""
        clock = MockClock()
        limiter = BinanceRateLimiter(clock=clock)

        # Simulate a BinanceClientError with a 429 status
        err_type = type("BinanceClientError", (Exception,), {})
        err = err_type("API rate limit exceeded")
        err.status_code = 429

        with patch("random.uniform", return_value=0.0):
            result = limiter.handle_error(err, retry_count=0)
            assert result == 1.0

