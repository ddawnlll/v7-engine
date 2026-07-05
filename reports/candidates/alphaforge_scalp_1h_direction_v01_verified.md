# ALPHAFORGE_SCALP_1H_DIRECTION_V01 — VERIFIED (Phase 1 Complete)

**Date:** 2026-07-05 21:55 UTC
**Status:** PHASE1_VERIFIED — gross/net audit PASS, block-bootstrap CI fully positive

## Phase 1 Audit Results

| Check | Status | Detail |
|-------|--------|--------|
| 1a Gross/Net | PASS | Cost deducted in label generator (authority={ROUND_TRIP_COST_BPS:.0f}bps round trip) |
| 1b Block Bootstrap | PASS | Aggregate CI=[0.0076, 0.0086], All folds positive=True |
| 1c Threshold Audit | PASS | DISABLED, no data leakage, purge/embargo active |

## Aggregate CI: [0.0076, 0.0086]

  Fold 1: net_R=0.006546 CI=[0.0059, 0.0072] ✅
  Fold 2: net_R=0.005666 CI=[0.0052, 0.0062] ✅
  Fold 3: net_R=0.005479 CI=[0.0050, 0.0060] ✅
  Fold 4: net_R=0.007843 CI=[0.0073, 0.0084] ✅
  Fold 5: net_R=0.010511 CI=[0.0095, 0.0116] ✅
  Fold 6: net_R=0.012559 CI=[0.0116, 0.0136] ✅

## DataPassport
- Source: binance
- Real data: True
- Coverage: 100.0%

## Status

**PHASE1_VERIFIED** — Real data edge confirmed with cost audit and block-bootstrap CI.

## Next Step

- Phase 2: Feature ablation on real data (DoubleEnsemble shuffle)
- Phase 3: Threshold re-optimization on pruned feature set
