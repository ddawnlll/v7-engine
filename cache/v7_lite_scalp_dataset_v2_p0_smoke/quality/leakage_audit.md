# Leakage Audit — V2 P0 Smoke

Generated: 2026-07-09T10:21:35.219433+00:00

## Join Configuration

- **Method**: As-of backward join
- **Tolerance**: 5 minutes
- **Direction**: backward (observable at or before bar close)

## Quality Flags

- **Unknown delay**: All overlay sources marked as unknown publication delay
- **Stale data**: Flagged when overlay data is >1 hour old

## Join Results

- **okx_trades**: PASS (168 rows)
- **bybit_oi**: BLOCKED (0 rows)
- **bybit_funding**: BLOCKED (0 rows)
