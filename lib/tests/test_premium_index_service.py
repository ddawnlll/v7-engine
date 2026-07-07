"""Tests for PremiumIndexService."""
from lib.market_data.binance.premium_index_service import PremiumIndexService, PremiumIndexRecord


class _FakeClient:
    def get_premium_index_klines(self, symbol="BTCUSDT", interval="1h",
                                  start_time=None, end_time=None, limit=1000):
        return [[1700000000000, 100.5, 101.2, 99.8, 100.7, 50000.0]]


def test_fetch_returns_records():
    service = PremiumIndexService(_FakeClient())
    records = service.fetch("BTCUSDT", "1h", 1700000000000, 1700086400000)
    assert len(records) == 1
    assert isinstance(records[0], PremiumIndexRecord)
    assert records[0].symbol == "BTCUSDT"
    assert records[0].premium_close == 100.7
    assert records[0].index_price == 50000.0


def test_fetch_empty_on_no_data():
    class _EmptyClient:
        def get_premium_index_klines(self, **kwargs):
            return []
    service = PremiumIndexService(_EmptyClient())
    records = service.fetch("BTCUSDT", "1h")
    assert records == []
