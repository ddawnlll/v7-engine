# Alpha Rescue Autopsy — Run Summary

**Generated:** 2026-07-08
**Previous V7-Lite claimed readiness:** 62.5%
**Corrected readiness after hard caps:** **45%**

---

## Hard Cap Analysis

The 62.5% score from the previous run was **infrastructure-skewed**.
The calibration control plane, outcome cache, and parity tests inflated the
score without addressing the fundamental problem: no alpha is cost-positive.

Applying the task's hard caps:

```yaml
hard_caps:
  if cost_adjusted_positive_alpha_count == 0:
    max_overall_readiness: 45        # ← THIS APPLIES (0 cost-adjusted)

  if promotion_ready_alpha_count == 0:
    max_overall_readiness: 50        # ← WOULD ALSO APPLY

  if holdout_passed_alpha_count == 0:
    max_overall_readiness: 55        # ← WOULD ALSO APPLY

  if independent_promoted_clusters < 3:
    max_revenue_readiness: 15        # ← WOULD ALSO APPLY
```

**Corrected overall readiness: 45%** (capped by the 0 cost-survivors rule)
**Revenue readiness: 0%** (0 cost-survivors, 0 promoted clusters, 0 holdout passes)

---

## Current vs Corrected

| Component | Previous Claim | Corrected |
|-----------|---------------|-----------|
| Infrastructure readiness | 62.5% | 45% |
| Alpha discovery readiness | 65% | 30% |
| Cost survival readiness | 25% | 5% |
| Revenue readiness | 3% | 0% |
| **Overall** | **62.5%** | **45%** |

The reason: 62.5% was infrastructure-subjective (having a parity test suite
is good, but it doesn't make alphas profitable). The hard cap correctly
recognizes that without at least one cost-surviving alpha, the system
cannot exceed 45% overall readiness.

---

## Alpha Inventory Health

| Metric | Value | Trend |
|--------|-------|-------|
| Raw-positive alphas | 3 | Stable (need 10) |
| Cost-adjusted positive | 0 | Blocked (need 3) |
| Promotion-ready | 0 | Blocked (need 1) |
| True independent clusters | ~4 | Stable |
| Inversion candidates (high priority) | 6 | Ready to test |
| Segment rescue candidates | 9 | Need filtering |
| Permanently rejected | 5 | Cleared |
| Near-zero noise | 3 | Cleared |
| Contaminated | 1 | Cleared |
| Proxy-only (need central sim) | 33 | Blocked |

---

## Realistic Targets

| Timeframe | Raw-positive | Cost-survivors | Promotion |
|-----------|-------------|----------------|-----------|
| Current | 3 | 0 | 0 |
| After 6 inversions | 6-7 | 0 | 0 |
| After 9 segment rescues | 6-8 | 0-1 | 0 |
| After cost optimization | 5-8 | 1-2 | 0 |
| After new discovery | 8-12 | 1-3 | 0-1 |

**Realistic ceiling without new alpha discovery:** 7 raw-positive, 1-2 cost-survivors
**Realistic ceiling WITH new alpha discovery:** 10 raw-positive, 2-3 cost-survivors, 0-1 promotion

---

## Files Created

| File | Description |
|------|-------------|
| `NEGATIVE_ALPHA_AUTOPSY_REPORT.md` | Full autopsy of all 170 entries |
| `ALPHA_RESCUE_MATRIX.csv` | 170-row classification matrix |
| `ALPHA_RESCUE_MATRIX.json` | JSON version |
| `INVERSION_CANDIDATES.md` | 36 inversion candidates analyzed |
| `SEGMENT_RESCUE_CANDIDATES.md` | 9 segment rescue candidates |
| `COST_RESCUE_CANDIDATES.md` | Cost rescue analysis |
| `REJECT_FOREVER_LIST.md` | 5 permanently rejected |
| `ALPHA_CLUSTER_MAP.md` | 11 clusters mapped |
| `NEXT_10_ALPHA_DISCOVERY_PLAN.md` | 10 proposed experiments |
| `run_summary.md` | This file |
