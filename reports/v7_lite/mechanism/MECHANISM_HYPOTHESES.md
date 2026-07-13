# Mechanism Hypotheses — Issue #290

**Generated:** 2026-07-08T15:10:00Z

## Context

After #286 (TEMIZ) and #287 (KIRMIZI), the mining-based symbol-specialist approach is terminated. This document defines mechanism hypotheses for surviving alphas and pre-registered test plans.

## Raw-Positive Alphas Analysis

### 1. Truth V6 (Discovery Pipeline V6)
- **Raw R:** +0.0515 (870 trades)
- **Status:** REJECTED (KIRMIZI after OOS)
- **Mechanism hypothesis:** NOT APPLICABLE — edge confirmed as noise
- **Action:** Closed. No further testing.

### 2. BB Position Mean-Reversion v1 → v2
- **v1 Raw R:** +0.0043 (4552 trades)
- **v1 Status:** CONTAMINATED (leakage in _rolling_mean feature)
- **v2 Verdict (2026-07-13):** KIRMIZI (REJECT) — see BB_POSITION_V2_REVALIDATION.md
- **v2 Net R:** +0.012144 (521 active trades, 6-fold WFV, corrected PIPELINE_VERSION 0.3.1)
- **v2 Cost stress:** FAIL_EDGE_DESTROYED_BY_COSTS (break-even: 1.23x baseline)
- **Mechanism hypothesis:** NOT SUPPORTED. The edge exists as a statistical trace (+0.012R/trade, z=10.57 vs null) but is too weak to survive normal operating costs. The model's 97% low-confidence rate and 1.7% exposure make it practically unusable.
- **Why it might work:** N/A — hypotez reddedildi.
- **Why it might NOT work:** The bb_position feature, even corrected, does not produce a reliable economic signal. Mean-reversion signal is too rare (1.7% exposure) and too weak to cover costs. The mechanism is not actionable.
- **Pre-registered test symbols:** BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT — tested as specified.
- **Test plan:** ✅ Complete. Result: KIRMIZI. See BB_POSITION_V2_REVALIDATION.md for full protocol execution.

### 3. SCALP 1h Direction v01
- **Raw R:** +0.0076 (31752 trades)
- **Status:** REJECTED (too weak, no actionability)
- **Mechanism hypothesis:** "XGBoost can extract short-term directional signals from 1h OHLCV features (momentum, volume, volatility regimes). The 2-class LONG/SHORT formulation captures net directional bias."
- **Why it might work:** Large trade count suggests statistical robustness. XGBoost can capture non-linear feature interactions.
- **Why it might NOT work:** Edge is +0.0076R — barely above noise. 2-class formulation means no NO_TRADE filtering. High trade count with tiny edge = survivorship bias risk.
- **Pre-registered test symbols:** Same 4, but with NO_TRADE class added (3-class formulation).
- **Test plan:** Re-run with 3-class (LONG/SHORT/NO_TRADE) and check if edge survives filtering.

## Decision

Since Truth V6 is rejected and BB Position v1 is contaminated:

- **BB Position v2** (corrected) is the only viable candidate for mechanism testing. Needs revalidation first.
- **SCALP 1h Direction** has an edge too weak to justify further investigation without significant improvement.
- **No new mining** is allowed. Only mechanism-driven testing of existing candidates.

## Next Steps

1. Revalidate BB Position v2 with corrected features (priority)
2. If BB v2 survives: mechanism hypothesis test with OOS
3. If BB v2 fails: entire alpha pipeline needs fundamental redesign
4. #288 (rails) runs in parallel regardless
