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
| Rate limiter | `lib/market_data/binance/rate_limiter.py` | Token-bucket rate limiter (Binance weight-aware) |
| Checkpoint | `lib/market_data/binance/checkpoint.py` | JSON checkpoint save/resume for backfill |
| Storage writer | `lib/market_data/storage.py` | Parquet writer with SHA-256 checksum sidecars |
| Data catalog | `lib/market_data/catalog.py` | JSON catalog tracking ingested symbol/interval/ranges |
| Backfill orchestrator | `lib/market_data/binance/backfill.py` | Ties all components into backfill workflow |

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

## Backfill Architecture

```
BackfillOrchestrator
  ├── KlinesService        (fetch klines with pagination)
  ├── FundingService       (fetch funding rates)
  ├── BinanceRateLimiter   (weight-based rate limiting)
  ├── BackfillCheckpoint   (resume interrupted backfills)
  ├── StorageWriter        (write raw + normalized Parquet + .sha256)
  └── DataCatalog          (track what's been ingested)
```

### File naming

```
data/raw/{SYMBOL}/{SYMBOL}_{interval}_{start_ms}_{end_ms}.parquet
data/normalized/{SYMBOL}/{SYMBOL}_{interval}_{start_ms}_{end_ms}.parquet
data/normalized/{SYMBOL}/funding_{SYMBOL}_{start_ms}_{end_ms}.parquet
```

Each Parquet has a `.sha256` sidecar for integrity verification.

### Checkpoint resume

The `BackfillCheckpoint` records completed (symbol, interval, time_range)
combinations.  Before backfilling a range the orchestrator checks the
checkpoint -- already-completed ranges are skipped.

## Consumption Pattern

```
lib/market_data/binance/  ──►  v7/state/ (builds canonical state)
lib/market_data/binance/  ──►  alphaforge/features/ (builds feature matrices)
```

Both systems call the same service. Each interprets the result differently.
