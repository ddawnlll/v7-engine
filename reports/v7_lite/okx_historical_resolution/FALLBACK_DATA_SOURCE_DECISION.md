# Fallback Data Source Decision

## Problem
OKX public API does NOT provide historical trade/tick data.
Only OHLCV candles (375 days) and funding (33 days) are available historically.

## Fallback Options

| Source | Data Type | Cost | Historical Depth | Recommendation |
|--------|-----------|------|------------------|----------------|
| Tardis.dev (free tier) | Trade ticks | Free limited | Full exchange history | TOP PICK — academically oriented |
| Kaiko | Trade ticks | Paid | Full history | Enterprise grade |
| CoinAPI | Trade ticks | Paid | Years | Good REST API |
| OKX Excel download (manual) | Trades per month | Free + manual | Manual effort | Lower effort but not automated |
| Continue with OKX candles+funding only | OHLCV + funding | Free | 375+33 days | Acceptable fallback |

## Decision
**RECOMMENDATION**: Continue with OKX funding (33 days) + OKX candles (375 days) for now.
Tardis.dev free tier should be evaluated for historical trade ticks when needed for specialist scan.
OKX REST/historical-trades is RECENT ONLY — cannot build historical trade feature dataset from it.
