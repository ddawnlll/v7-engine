# OKX Historical Schema Audit

## Trades (history-trades endpoint)
- EXISTS but RECENT ONLY
- Returns ~100 trades per page, max ~5000 via pagination
- Same data as regular trades endpoint
- Rejects historical `after` parameters
- Schema: instId, side, sz, px, tradeId, ts

## Funding (funding-rate-history endpoint)
- HISTORICAL: returns up to 199 rows covering ~33 days
- Paginates with `before` parameter
- Schema: fundingTime, fundingRate, instId, realizedRate

## Candles (history-candles endpoint)
- HISTORICAL: years of data via `after` pagination
- Max 300 rows per call, can chain arbitrarily
- 9000 1h candles = 375 days
- Schema: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
