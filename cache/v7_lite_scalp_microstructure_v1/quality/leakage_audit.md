# Leakage Audit — V7-Lite Scalp Microstructure V1

Generated: 2026-07-09T07:59:46.974461+00:00

## Timestamp Semantics

| Feature Group | Timestamp Meaning | Leakage Risk |
|---------------|-------------------|--------------|
| OHLCV 1h/4h | Bar open time | SAFE |
| Funding rate | Funding timestamp | SAFE |
| Open interest | Period open time | SAFE |
| Premium index | Bar open time | SAFE |
| Taker volume | Bar open time (from klines) | SAFE |
| aggTrade features | NOT AVAILABLE (API blocked) | N/A |

## Join Safety

All joins use backward-looking merge_asof with direction='backward'.
No future data leakage possible.

## Conclusion

- OHLCV, funding, OI, premium, taker volume: **SAFE**
- aggTrade features: **NOT AVAILABLE** (Binance API geo-blocked)
