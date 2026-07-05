"""Tests for runtime/services/utils.py."""

from runtime.services.utils import interval_minutes, to_float, utc_now_iso


class TestUtcNowIso:
    def test_returns_string(self):
        result = utc_now_iso()
        assert isinstance(result, str)
        assert "T" in result
        assert result.endswith("+00:00") or result.endswith("Z")


class TestToFloat:
    def test_none(self):
        assert to_float(None) is None

    def test_number(self):
        assert to_float(42) == 42.0

    def test_string_number(self):
        assert to_float("3.14") == 3.14

    def test_invalid_string(self):
        assert to_float("abc") is None

    def test_zero(self):
        assert to_float(0) == 0.0


class TestIntervalMinutes:
    def test_empty(self):
        assert interval_minutes("") == 60

    def test_minutes(self):
        assert interval_minutes("15m") == 15

    def test_hours(self):
        assert interval_minutes("4h") == 240

    def test_days(self):
        assert interval_minutes("1d") == 1440

    def test_weeks(self):
        assert interval_minutes("1w") == 10080

    def test_month(self):
        assert interval_minutes("1M") == 43200

    def test_month_lower(self):
        assert interval_minutes("1mo") == 43200

    def test_invalid_suffix(self):
        assert interval_minutes("10x") == 60

    def test_non_digit_prefix(self):
        assert interval_minutes("ab") == 60

    def test_case_insensitive_hours(self):
        assert interval_minutes("4H") == 240
