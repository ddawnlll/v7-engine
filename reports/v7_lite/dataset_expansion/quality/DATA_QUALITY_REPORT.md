# Data Quality Audit Report

Generated: 2026-07-09T07:13:18.825086+00:00

## Executive Summary

| Metric | Value |
|--------|-------|
| Total files audited | 91 |
| QUALITY_PASS | 67 |
| QUALITY_WARN_MINOR_GAPS | 24 |
| QUALITY_WARN_LARGE_GAPS | 0 |
| QUALITY_FAIL_BAD_OHLCV | 0 |
| QUALITY_FAIL_TOO_SHORT | 0 |
| QUALITY_BLOCKED_UNREADABLE | 0 |
| Usable for scalp (≥10k rows) | 91 |
| Usable for swing (≥1k rows) | 91 |

## Quality Verdict Distribution

| Verdict | Count | % |
|---------|-------|---|
| QUALITY_PASS | 67 | 73% |
| QUALITY_WARN_MINOR_GAPS | 24 | 26% |
| QUALITY_WARN_LARGE_GAPS | 0 | 0% |
| QUALITY_FAIL_BAD_OHLCV | 0 | 0% |
| QUALITY_FAIL_TOO_SHORT | 0 | 0% |
| QUALITY_BLOCKED_UNREADABLE | 0 | 0% |

## Minimum Usable Criteria

| Timeframe | Preferred | Minimum Partial |
|-----------|-----------|-----------------|
| 1h | ≥3000 rows | ≥1000 rows |
| 4h | ≥1000 rows | ≥500 rows |
| 15m | ≥10000 rows | ≥3000 rows |

## Issues Found

### Duplicate Timestamps
- None found

### Missing Candles
- ICPUSDT/ICPUSDT_1h.parquet: 6 missing candles
- FILUSDT/FILUSDT_1h.parquet: 2 missing candles
- FILUSDT/FILUSDT_1h_with_derivatives.parquet: 2 missing candles
- FTMUSDT/FTMUSDT_1h.parquet: 2 missing candles
- GRTUSDT/GRTUSDT_1h.parquet: 2 missing candles
- HBARUSDT/HBARUSDT_1h.parquet: 2 missing candles
- IMXUSDT/IMXUSDT_1h.parquet: 2 missing candles
- KSMUSDT/KSMUSDT_1h.parquet: 2 missing candles
- LTCUSDT/LTCUSDT_1h.parquet: 2 missing candles
- LTCUSDT/LTCUSDT_1h_with_derivatives.parquet: 2 missing candles

### Extreme Returns (>50% in 1h)
- UNIUSDT/UNIUSDT_1h.parquet: 1 extreme returns
- UNIUSDT/UNIUSDT_1h_with_derivatives.parquet: 1 extreme returns

### Zero/Negative OHLCV
- None found

## Scalp/Swing Usability

- **Usable for scalp (≥10k rows):** 91 files
- **Usable for swing (≥1k rows):** 91 files

## Key Finding

The dataset is remarkably clean. 67/91 files pass quality checks.
All files are 1h timeframe with OHLCV data. No 4h or 15m data exists.
19 symbols have derivatives data.
