# Timestamp Semantics — OKX Historical

- Trade timestamp: ms since epoch (trade execution time)
- Candles timestamp: bar open time (ms since epoch)
- Funding timestamp: funding time (ms since epoch)
- Is data observable in real time: YES (trade execution time)
- Does provider revise/backfill: NO
- As-of backward join safe: YES
- Safe decision timestamp: trade execution ts
- Unknown delays: true (publication delay unknown)
