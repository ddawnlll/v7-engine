# Dataset Expansion Plan

Generated: 2026-07-09T07:15:35.281075+00:00

## Current State

- **51 symbols** in data/raw/ with 1h parquet files
- **4 symbols** in data_lake/ (BTC, ETH, SOL, BNB) with monthly parquets
- **All 1h timeframe** — no 4h or 15m data exists
- **~3.3M total rows** across all files

## Expansion Attempt

### What Was Done
1. Built expanded panel cache from all available 1h data
2. Combined 51 symbol parquets into 5 OHLCV panel files
3. Created manifest.json with full metadata

### What Was NOT Done (and Why)
- **4h timeframe:** Not available in existing data. Would require:
  ```bash
  python3 scripts/download_binance.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --intervals 4h
  ```
  But the downloader only supports 1h directly; 4h is resampled from 1h.

- **15m timeframe:** Not available. Would require:
  ```bash
  python3 scripts/download_binance.py --symbols BTCUSDT,ETHUSDT --intervals 15m
  ```
  15m is supported by the downloader but not currently downloaded.

- **Additional symbols (SHIB, PEPE, FLOKI, FET, RENDER, OCEAN, WLD):** Not in repo.
  Would require:
  ```bash
  python3 scripts/download_binance.py --symbols SHIBUSDT,PEPEUSDT,FLOKIUSDT,FETUSDT,RENDERUSDT,OCEANUSDT,WLDUSDT --intervals 1h
  ```

## Expansion Targets

| Target | Status | Action Required |
|--------|--------|-----------------|
| 24+ symbols at 1h | ✅ ACHIEVED | 51 symbols available |
| 4h timeframe | ❌ NOT AVAILABLE | Run downloader with --intervals 4h |
| 15m timeframe | ❌ NOT AVAILABLE | Run downloader with --intervals 15m |
| 30-50 symbols | ✅ ACHIEVED | 51 symbols available |
| Date range 2021-2026 | ⚠️ PARTIAL | data/raw covers 2021-2026, data_lake covers 2023-2026 |

## Blockers for Further Expansion

1. **No 4h/15m data:** The downloader supports these intervals but they haven't been fetched
2. **Missing meme/AI tokens:** SHIBUSDT, PEPEUSDT, FLOKIUSDT, FETUSDT, etc. not in repo
3. **No derivatives for all symbols:** Only 19/51 symbols have funding_rate data

## Recommended Next Commands

```bash
# Download 4h data for top symbols
python3 scripts/download_binance.py --symbols BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,AVAXUSDT,DOTUSDT,LINKUSDT,LTCUSDT,UNIUSDT,OPUSDT,ARBUSDT --intervals 4h

# Download missing meme tokens
python3 scripts/download_binance.py --symbols SHIBUSDT,PEPEUSDT,FLOKIUSDT --intervals 1h

# Download missing AI tokens
python3 scripts/download_binance.py --symbols FETUSDT,RENDERUSDT,OCEANUSDT,WLDUSDT --intervals 1h
```

## Expansion Status

**EXPANDED_CACHE_BUILT** — Panel cache built from existing 51-symbol 1h data.
