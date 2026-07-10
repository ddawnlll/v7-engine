# Central Pipeline Join Report — V2 P0 Smoke

Generated: 2026-07-09T10:21:22.797549+00:00

## Can V2 features be loaded?
- OKX trade features: NO
- Bybit OI: NO
- Bybit funding: NO

## Can V2 features be joined to factor signal events?
- Join status: PASS

## Can enriched signal events be passed to central simulation bridge?
- Enriched sample exists: /teamspace/studios/this_studio/v7-engine/reports/v7_lite/dataset_v2_p0_smoke/enriched_signal_events_sample.csv

## What exact code path would read these features?
- `scripts/v7_lite/join_v2_features_to_signal_events.py`
- As-of backward join with 5-minute tolerance

## What blockers remain?
- OKX/Bybit reachability (if blocked)
- Feature extraction (if raw data unavailable)
- Join quality (if data is stale or has gaps)
