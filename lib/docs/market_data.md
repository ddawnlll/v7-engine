# Shared Market Data Service

## Scope

Only the raw data fetching layer is shared. The *interpretation* of market data (V7 canonical state vs AlphaForge feature matrices) is NOT shared.

## What's Shared

| Component | File | Description |
|---|---|---|
| Binance HTTP client | `lib/market_data/binance/client.py` | Low-level API calls, retry/backoff, pagination |
| Klines service | `lib/market_data/binance/klines_service.py` | Fetch + cache klines by symbol/interval/range |
| Funding rate service | `lib/market_data/binance/funding_service.py` | Fetch funding rate history |
| Market data service | `lib/market_data/binance/market_data_service.py` | Orchestration: multi-symbol, cache-aware, quality reports |
| Standard schema | `lib/market_data/contracts.py` | KlineRecord, MarketDataResult, DataQualityReport |
| Quality checks | `lib/market_data/quality.py` | Gap detection, duplicate detection, completeness |

## Kline Schema

```python
@dataclass
class KlineRecord:
    symbol: str
    timestamp: int          # Unix ms
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trade_count: int
    taker_buy_volume: float
    taker_buy_quote_volume: float
    interval: str
    source: str
    is_closed: bool
```

## Consumption Pattern

```
lib/market_data/binance/  ──►  v7/state/ (builds canonical state)
lib/market_data/binance/  ──►  alphaforge/features/ (builds feature matrices)
```

Both systems call the same service. Each interprets the result differently.
