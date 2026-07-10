# FACTOR_SIGNAL_EVENTS Schema

**Generated:** 2026-07-08T09:23:39Z

## Required Columns

| Column | Type | Description |
|--------|------|-------------|
| event_id | string | Unique event identifier |
| alpha_name | string | Alpha identifier (factor + config + side) |
| factor_name | string | Factor name from leaderboard |
| symbol | string | Trading pair (e.g. BTCUSDT) |
| timestamp | string | ISO timestamp of signal |
| timeframe | string | Signal timeframe (1h, 4h, 12h, 24h) |
| direction | string | LONG or SHORT |
| signal_value | float | Computed factor value at signal time |
| entry_condition | string | Threshold condition that triggered signal |
| entry_price | float | Close price at signal time |
| atr | float | 14-bar ATR at signal time |
| source_file | string | Generator script name |
| source_row_id | string | Source identifier for traceability |

## Factor Sources

- **breakdown_n_low** (short, 24h): N-period low breakdown — short when price breaks below N-period low
- **volume_zscore** (long, 24h): Volume Z-score — long on unusual volume expansion
- **ret_24h_rank** (long, 24h): 24h return rank — long on strong momentum
- **ret_4h_rank** (long, 1h): 4h return rank — long on short-term momentum
- **reversal_4h_zscore** (long, 1h): 4h reversal Z-score — long on mean-reversion oversold
- **trend_pullback_ema** (long, 24h): Trend pullback to EMA — long when price pulls back in uptrend
- **ret_12h_rank** (long, 12h): 12h return rank — medium-term momentum
- **ret_1h_rank** (long, 1h): 1h return rank — short-term momentum
- **reversal_1h_zscore** (long, 1h): 1h reversal Z-score — short-term mean reversion
- **range_zscore** (long, 24h): Range Z-score — long on expanding range
- **compression_breakout_regime** (long, 24h): Compression breakout — long when BB width compresses
- **spread_contraction_signal** (long, 24h): Spread contraction — long on tightening spreads
