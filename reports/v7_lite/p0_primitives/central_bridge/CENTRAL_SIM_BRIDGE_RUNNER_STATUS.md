# Central Simulation Bridge Runner Status

**Generated:** 2026-07-08T09:30:00Z

## Run Summary

| Metric | Value |
|--------|-------|
| Events input | 40,091 |
| Events processed | 40,090 (99.998%) |
| Success rate | 100.0% |
| Mean directional R | -0.0687 |
| Cost-adjusted mean R | -0.1211 |
| Cost per trade R | 0.0524 |

## Best Action Distribution

| Action | Count | % |
|--------|-------|---|
| NO_TRADE | 17,140 | 42.8% |
| AMBIGUOUS_STATE | 9,667 | 24.1% |
| SHORT_NOW | 6,737 | 16.8% |
| LONG_NOW | 6,546 | 16.3% |

## Per-Factor Results

| Factor | Events | Mean R | Cost-Adj R | Raw Positive % |
|--------|--------|--------|------------|----------------|
| ret_12h_rank | 2,993 | -0.0368 | -0.0892 | 46.4% |
| ret_4h_rank | 4,525 | -0.0393 | -0.0917 | 46.4% |
| volume_zscore | 3,692 | -0.0473 | -0.0996 | 46.3% |
| range_zscore | 1,408 | -0.0610 | -0.1134 | 45.9% |
| compression_breakout_regime | 1,266 | -0.0669 | -0.1193 | 47.2% |
| reversal_1h_zscore | 2,707 | -0.0723 | -0.1247 | 44.8% |
| reversal_4h_zscore | 1,756 | -0.0744 | -0.1267 | 44.9% |
| trend_pullback_ema | 3,494 | -0.0764 | -0.1288 | 45.3% |
| ret_24h_rank | 2,523 | -0.0765 | -0.1289 | 44.5% |
| breakdown_n_low | 7,502 | -0.0843 | -0.1367 | 43.9% |
| ret_1h_rank | 5,653 | -0.0836 | -0.1360 | 44.4% |
| spread_contraction_signal | 2,568 | -0.0895 | -0.1419 | 45.6% |

## Key Findings

1. **All 12 factors have negative mean R through central simulation.** The best is `ret_12h_rank` at -0.0368R.
2. **45% of individual trades are raw positive**, but the losers are larger than the winners.
3. **NO_TRADE is the most common best action (42.8%)** — the central engine correctly identifies most factor signals as not actionable.
4. **No factor survives cost adjustment.** Even the best factor (-0.0368R) loses -0.0892R after costs.
5. **This is expected.** The factor sprint leaderboard already showed all factors as REJECT with negative total R.

## Verdict

**CENTRAL_BRIDGE_RAN_REAL_DATA** — 40,090 events processed through central simulation. All factor signals show negative expectancy. This confirms the leaderboard findings at the simulation engine level.

## Usage

The results CSV can be used for:
- Factor-by-factor analysis
- Signal quality filtering
- Regime-aware signal selection
- Cost sensitivity analysis
