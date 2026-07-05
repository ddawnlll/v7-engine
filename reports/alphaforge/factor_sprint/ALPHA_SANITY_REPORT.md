# Alpha Sanity Report — Factor Sprint 001

Generated: 2026-07-04T07:26:32.155071

## ALPHA_LEADERBOARD.csv Sanity Checks

✅ File exists: 48 rows
✅ All required columns present
✅ At least 12 candidates: 12 unique factors
- Horizons tested: [np.int64(1), np.int64(4), np.int64(12), np.int64(24)]
✅ Minimum symbol count: 20 (>= 10)
- PASS: 0
- WATCH: 45
- FAIL: 3
✅ IC NaN rate: 0.0%
- Date range: 2023-01-01 01:00:00+00:00 to 2026-05-31 22:00:00+00:00

## ALPHA_R_LEADERBOARD.csv Sanity Checks

✅ File exists: 33 rows
✅ All required columns present
✅ All configurations have trades (min: 27491)
- PROMOTE_TO_MINI_V7: 0
- WATCH: 0
- REJECT: 33
- Average fee drag: 14633.9464 R

## Cross-Check: IC × R Consistency

⚠️ No IC-PASS factor also achieves R-PROMOTE

## Overall Verdict

📊 **NEGATIVE EVIDENCE** — All candidates rejected. This is valuable: the lab measured deterministic alphas honestly.
