"""Tests for OpenInterestService."""
from lib.market_data.binance.open_interest_service import OpenInterestService, OpenInterestRecord


class _FakeClient:
    def get_open_interest_hist(self, symbol="BTCUSDT", period="1h",
                                start_time=None, end_time=None, limit=500):
        """Binance openInterestHist raw format: [timestamp, sumOI, sumOIValue]."""
        return [[1700000000000, 50000.0, 45000.0]]


def test_fetch_returns_records():
    service = OpenInterestService(_FakeClient())
    records = service.fetch("BTCUSDT", start_time=1700000000000, end_time=1700086400000)
    assert len(records) == 1
    assert isinstance(records[0], OpenInterestRecord)
    assert records[0].symbol == "BTCUSDT"
    assert records[0].timestamp == 1700000000000
    assert records[0].open_interest == 50000.0
    assert records[0].open_interest_value == 45000.0


def test_fetch_empty_on_no_data():
    class _EmptyClient:
        def get_open_interest_hist(self, **kwargs):
            return []
    service = OpenInterestService(_EmptyClient())
    records = service.fetch("BTCUSDT")
    assert records == []
