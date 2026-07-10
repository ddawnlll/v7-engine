# Storage Budget Report

Generated: 2026-07-09T07:59:59Z

## Permanent Dataset

| Path | Size | Notes |
|------|------|-------|
| ohlcv/klines_1h.parquet | ~30 MB | 56 symbols, 2.1M rows |
| ohlcv/klines_4h.parquet | ~8 MB | 56 symbols, 524K rows |
| derivatives/funding_rate.parquet | ~12 MB | 19 symbols, 680K rows |
| derivatives/open_interest.parquet | ~12 MB | 19 symbols, 680K rows |
| derivatives/premium_index_klines.parquet | ~12 MB | 19 symbols, 680K rows |
| manifest.json | ~2 KB | Metadata |
| quality/ | ~5 KB | Audit files |
| registry/ | ~5 KB | Feature matrix |
| logs/ | ~2 KB | Smoke test log |
| **Total** | **~0.06 GB** | |

## Budget

| Metric | Value |
|--------|-------|
| Permanent size | 0.06 GB |
| Hard cap | 100 GB |
| Utilization | 0.06% |
| Remaining | 99.94 GB |

## Future Expansion

If API access is restored, estimated additional storage:

| Feature | Est. Size | Notes |
|---------|-----------|-------|
| 15m klines (16 symbols, 6 months) | ~2 GB | ~100K rows per symbol |
| aggTrade features (16 symbols, 3 months) | ~4 GB | 5m/15m/1h buckets |
| Taker buy/sell volume | ~1 GB | From klines endpoint |
| Mark price klines | ~2 GB | 10 symbols, full range |
| **Total potential** | **~9 GB** | |

Even with full expansion, well under 100 GB cap.
