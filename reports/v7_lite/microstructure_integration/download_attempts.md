# Download Attempts Log

Generated: 2026-07-09T07:59:59Z

## Summary

All Binance REST API calls returned HTTP 451 (Unavailable For Legal Reasons).
This is a geo-restriction — the server is in a region where Binance blocks access.

## Attempted Endpoints

| Endpoint | Symbol | Status | Error |
|----------|--------|--------|-------|
| /api/v3/klines?interval=15m | BTCUSDT | 451 | geo-blocked |
| /api/v3/klines?interval=15m | ETHUSDT | 451 | geo-blocked |
| /api/v3/klines?interval=15m | SOLUSDT | 451 | geo-blocked |
| /fapi/v1/fundingRate | AAVEUSDT | 451 | geo-blocked |
| /fapi/v1/fundingRate | ADAUSDT | 451 | geo-blocked |
| /fapi/v1/fundingRate | ALGOUSDT | 451 | geo-blocked |
| /fapi/v1/openInterestHist | BTCUSDT | 451 | geo-blocked |
| /fapi/v1/premiumIndexKlines | BTCUSDT | 451 | geo-blocked |
| /fapi/v1/aggTrades | BTCUSDT | 451 | geo-blocked |
| /fapi/v1/markPriceKlines | BTCUSDT | 451 | geo-blocked |

## What Worked (Local Data)

- ✅ Existing 1h parquets from data/raw/ (56 symbols)
- ✅ Existing _with_derivatives.parquet files (19 symbols with funding, OI, premium)
- ✅ 4h resample from 1h data

## What Failed (API Required)

- ❌ 15m klines (requires Binance API)
- ❌ Funding rate download (requires Binance API)
- ❌ Open interest download (requires Binance API)
- ❌ Premium index download (requires Binance API)
- ❌ aggTrades download (requires Binance API)
- ❌ Mark price klines (requires Binance API)
- ❌ Taker buy/sell volume (requires Binance API klines endpoint)

## Recommendations

1. **Run from non-restricted region** — Binance API works in most countries
2. **Use VPN** — route API calls through a non-restricted endpoint
3. **Use Binance Vision static files** — `scripts/download_binance.py` uses
   data.binance.vision (S3 mirror) which may work from this region
4. **Pre-download on local machine** — download data locally and upload to server
