# v0.30 — On-Chain Vendor Evidence Workflow

**Date:** 2026-07-02
**Status:** RESEARCH_COMPLETE — Pending implementation trigger (v0.30E+)

---

## 1. Core Rules (Hard — Never Violate)

```
1. ON-CHAIN DATA CANNOT GENERATE LABELS
   Labels must come from market outcomes (simulated or realized).
   On-chain data describes blockchain state, not market action quality.

2. ON-CHAIN DATA CANNOT BE GROUND TRUTH
   Ground truth for trading is: "what happened to the market after this state."
   On-chain metrics are features, not outcomes.

3. IF NOT POINT-IN-TIME SAFE:
   Backtest feature usage: FORBIDDEN
   Live/context usage: ALLOWED (with explicit DataPassport marker)

4. IF POINT-IN-TIME SAFE:
   Backtest feature usage: ALLOWED (with explicit DataPassport marker)
   PIT test must be re-run quarterly
   Only approved metrics may be used as features

5. VENDOR DATA COST MUST BE JUSTIFIED BY ALPHA IMPROVEMENT
   Before purchasing any vendor subscription:
   - Define specific hypothesis
   - Estimate expected alpha improvement
   - Compare cost vs projected benefit
   - Get explicit approval
```

---

## 2. Vendor Evaluation Summary

### 2.1 Glassnode — PRIMARY CANDIDATE

**PIT Safety:** ✅ Explicitly offers Point-in-Time metrics
**Cost:** High (Professional plan, not publicly priced)
**Coverage:** BTC, ETH + 1500 assets across 11 chains
**Data types:** On-chain fundamentals, derivatives, spot, ETFs, macro

**Assessment:**
Glassnode is the only vendor found with an explicit PIT guarantee. Their documentation states *"Point-in-Time metrics are immutable — they never receive retroactive updates."* This makes them the **only viable candidate** for backtest-safe on-chain features.

**Risk:** API cost. Professional plan likely $500+/mo. Must justify with specific alpha hypothesis before purchase.

### 2.2 CryptoQuant — DEFERRED

**PIT Safety:** ❌ No explicit PIT guarantee found
**Cost:** High
**Coverage:** Major chains, exchange flows, mining data

**Assessment:**
Without an explicit PIT guarantee, CryptoQuant data cannot be used for backtesting. Deferred until vendor provides PIT documentation.

### 2.3 Santiment — NOT RECOMMENDED

**PIT Safety:** ❌ Known mutation risk (`canMutate: true`)
**Cost:** Medium
**Coverage:** 2800+ assets, social + on-chain + dev

**Assessment:**
Santiment's own API docs show metrics with `canMutate: true` and stabilization periods. This is a **hard blocker** for backtest use. Social sentiment has limited value for major pair alpha. Not recommended for v0.30 scope.

---

## 3. PIT/Revision Test Protocol

### Phase 1 — 30-Day BTC Metric Fetch

**Purpose:** Initial PIT/revision screening
**Duration:** 7 days total (fetch + wait + refetch)

```
Day 1: Fetch daily BTC metrics for fixed 30-day range [T-60, T-30]
        Save as reference_snapshot_v1.json
        Metrics to fetch: [list specific Glassnode metric IDs]

Day 7: Refetch SAME range [T-60, T-30]
        Save as reference_snapshot_v2.json
        Run diff: compare v1 vs v2 field by field
        If ANY value differs: FAIL
        If all values match: PASS (preliminary)
```

**Output:** `reports/research/onchain_pit_test_phase1.md`

### Phase 2 — 180-Day Multi-Asset Fetch

**Purpose:** Extended PIT verification across assets and time
**Duration:** 14 days total

```
Day 1: Fetch BTC, ETH, USDT metrics for 180-day range [T-180, T-30]
        Save as reference_snapshot_v3.json

Day 14: Refetch SAME range
         Save as reference_snapshot_v4.json
         Run diff per metric per asset
         Generate comprehensive diff report
```

**Output:** `reports/research/onchain_pit_test_phase2.md`

### Phase 3 — Quarterly Re-Verification

**Purpose:** Ongoing PIT compliance
**Frequency:** Every 3 months

```
For each approved metric:
  1. Fetch last 90 days of data
  2. Save as reference
  3. Wait 7 days
  4. Refetch same range
  5. Diff
  6. If any diff: flag as PIT_FAIL and remove from approved list
```

---

## 4. Metric Evaluation Criteria

Each on-chain metric must pass these gates before becoming a feature:

```
Gate 1 — PIT Safety: Phase 1 test PASSED
Gate 2 — Data Quality: No gaps > 1 day in historical record
Gate 3 — Resolution: At minimum daily (hourly preferred)
Gate 4 — Coverage: Available for all target symbols
Gate 5 — Hypothesis: Specific alpha hypothesis documented
Gate 6 — Correlation check: Not > 0.95 correlated with existing features
Gate 7 — Cost check: Alpha improvement justifies data cost
```

---

## 5. Pilot Plan

### 5.1 Pre-Pilot (Before Any Purchase)

```
1. Document specific alpha hypothesis:
   "BTC exchange inflow/outflow predicts short-term volatility regime"
   "MVRV ratio provides context for trend exhaustion"
   
2. Define metric candidates:
   - Glassnode: exchange_net_flow, MVRV_ratio, realized_cap
   - BTC and ETH only (most reliable on-chain data)
   
3. Estimate feature value:
   - Would these features add independent signal?
   - Are they > 0.95 correlated with existing price-based features?
   - Estimated R improvement per trade?
```

### 5.2 Pilot (If Approved)

```
1. 30-day BTC metric fetch (Phase 1 PIT test)
2. If PASS: 180-day multi-asset fetch (Phase 2)
3. If PASS: Candidate metric list approved for feature research
4. Feature research: correlation analysis with existing features
5. If low correlation: ablation study with/without on-chain features
6. Decision point: does on-chain data improve alpha?
```

### 5.3 Post-Pilot

```
Verdict options:
- REJECT: No alpha improvement → drop on-chain data
- FEATURE_CONTEXT_ONLY: Some signal → add as optional feature group
- PRODUCTION: Clear improvement → integrate into standard feature pipeline
  (Only after PIT quarterly verification established)
```

---

## 6. Sample Workflow: Glassnode PIT Test

```python
# scripts/glassnode_pit_test.py — PIT/revision test harness

import json
import hashlib
from datetime import datetime, timedelta

def fetch_glassnode_metrics(api_key, metrics, assets, start, end):
    """Fetch metrics for a range. Save raw response."""
    results = {}
    for metric in metrics:
        for asset in assets:
            url = f"https://api.glassnode.com/v1/metrics/{metric}"
            params = {
                "a": asset,
                "s": start,
                "u": end,
                "api_key": api_key,
            }
            response = requests.get(url, params=params)
            results[f"{asset}/{metric}"] = response.json()
    return results

def pit_test_phase1(api_key, metric_ids, assets):
    """Run Phase 1 PIT test."""
    end = datetime.utcnow() - timedelta(days=30)
    start = end - timedelta(days=30)
    
    # Day 1: Fetch
    snapshot1 = fetch_glassnode_metrics(
        api_key, metric_ids, assets, start, end
    )
    save_snapshot(snapshot1, "pit_phase1_v1.json")
    
    # Wait 7 days (manual step)
    print("Day 1 complete. Come back in 7 days for refetch.")
    
def pit_compare(snapshot1_path, snapshot2_path):
    """Compare two snapshots. Any diff = FAIL."""
    with open(snapshot1_path) as f:
        v1 = json.load(f)
    with open(snapshot2_path) as f:
        v2 = json.load(f)
    
    diffs = []
    for key in v1:
        h1 = hashlib.sha256(json.dumps(v1[key], sort_keys=True).encode()).hexdigest()
        h2 = hashlib.sha256(json.dumps(v2[key], sort_keys=True).encode()).hexdigest()
        if h1 != h2:
            diffs.append(key)
    
    return {
        "passed": len(diffs) == 0,
        "diff_count": len(diffs),
        "diffs": diffs,
        "total_metrics": len(v1),
    }
```

---

## 7. Decision Points

| Question | Answer | Evidence |
|----------|--------|----------|
| Can on-chain data generate labels? | **NO — Hard Block** | Label source must be market outcomes |
| Can on-chain data be ground truth? | **NO — Hard Block** | Ground truth is simulated/realized P&L |
| Glassnode PIT safe? | **LIKELY YES** | Explicit PIT guarantee in docs |
| CryptoQuant PIT safe? | **UNKNOWN** | No PIT guarantee found |
| Santiment PIT safe? | **NO** | Known mutation (`canMutate: true`) |
| Purchase needed for v0.30? | **NO** | P0-P2 does not need on-chain data |
| When to re-evaluate? | **After v0.30E** | After real data baseline is stable |

---

## 8. Do-Not-Do List

- ❌ NEVER use on-chain data for label generation
- ❌ NEVER use on-chain data as ground truth
- ❌ NEVER purchase vendor subscription without alpha hypothesis
- ❌ NEVER skip PIT test before backtest feature use
- ❌ NEVER mix PIT-unsafe data with backtest features
- ❌ NEVER assume on-chain data improves alpha (test first)
- ❌ NEVER use social sentiment for trading decisions
