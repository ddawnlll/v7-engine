---
title: v0.25 Post-Run Research Analysis
subtitle: Did the diagnostic layer actually get repaired?
date: 2026-06-27
status: PARTIAL
generated_by: local_agent (read-only analysis)
---

# v0.25 Post-Run Research Analysis

## Executive Summary

**v0.25 diagnostics repair is PARTIALLY complete but cannot be verified.**

The workflow created all required code changes in isolated worktrees. However, the sync to `main` had a critical gap: the MHT correction module (`mht.py` + `test_mht.py`) was **never committed to git** — it exists only as an untracked file in worktree-9. Additionally, 6 of 14 intended schema new metric fields are missing on main, `test_schema_active_metrics.py` was committed then deleted in a subsequent sync, and **no rerun was performed** after any code change. All 6 canonical reports on main were generated **before** the fixes and show the exact old bug patterns.

**This is not a workflow logic failure — it's a sync gap.** The code works in worktree isolation but was not fully propagated to main.

---

## Issue Verdicts

| Issue | Verdict | Key Gap |
|-------|---------|---------|
| #123 Active Trade Metrics | **PASS_WITH_HOLDS** | Schema has 8/14 new fields (missing fee/slippage/funding R, avg_R_per_decision, turnover, avg_hold_bars). Reports not regenerated. |
| #124 MHT / Trial Ledger | **FAIL** | `mht.py` never committed to main. Exists only as untracked file in worktree-9. empirical.py on main still uses old MHT code. |
| #125 6-Fold WFV | **PASS_WITH_HOLDS** | `walk_forward_validate()` on main but reports show fold_count=1 (pre-fix). Not verified in production. |
| #122 Centralized Summary | **PASS_WITH_HOLDS** | `run_summary.py` on main with 37 tests. But never executed — no `research_run_summary.json` exists. |

---

## Candidate Scoreboard

All 6 canonical reports are **pre-fix** and show identical bug patterns:

| Candidate | Verdict | Active Trades | Cost Stress | MHT | Folds | True Failure? |
|-----------|---------|--------------|-------------|-----|-------|---------------|
| SWING (185651) | REJECT | 0 (bug) | FAIL (empty) | NONE_APPLIED | 1 | UNKNOWN — reporting bug |
| SWING (185736) | REJECT | 0 (bug) | FAIL (empty) | NONE_APPLIED | 1 | UNKNOWN — reporting bug |
| SWING (203209) | REJECT | 0 (bug) | FAIL (empty) | NONE_APPLIED | 1 | UNKNOWN — reporting bug |
| SWING (203241) | REJECT | 0 (bug) | FAIL (empty) | NONE_APPLIED | 1 | UNKNOWN — reporting bug |
| SCALP (185919) | REJECT | 0 (bug) | FAIL (empty) | NONE_APPLIED | 1 | UNKNOWN — reporting bug |
| AGGRESSIVE_SCALP (190716) | REJECT | 0 (bug) | FAIL (empty) | NONE_APPLIED | 1 | UNKNOWN — reporting bug |

**Common pre-fix bugs confirmed in all reports:**
- `oos_trade_count = 0` (no active trades computed)
- `active_trade_count` field MISSING (pre-schema)
- `fold_count = 1` (pre-6-fold WFV)
- `tested_hypothesis_count = 1` (pre-MHT)
- `correction_method = NONE_APPLIED` (pre-MHT)
- `trial_count_disclosure = 0` (pre-trial-ledger)
- `cost_stress_verdict = FAIL_EDGE_DESTROYED_BY_COSTS` (with empty stress levels)
- `edge_only_in_rare_regime = true` (contradictory — all regimes show edge_present=false)
- `active_beats_no_trade = false` (placeholder since oos_trade_count=0)
- "single symbol limitation" text in blocked_scopes despite 10 symbols in data_scope

---

## Top Root Causes

1. **MHT module never synced to main** (BLOCKING)
2. **Schema incomplete on main** — 6 of 14 new fields missing
3. **No post-fix rerun** — all reports show pre-fix bugs
4. **test_schema_active_metrics.py deleted** during second sync
5. **empirical.py on main has OLD MHT code** — uses `fold_count * hypotheses_per_fold`, not `trial_context.trial_count`

---

## Did v0.25 Succeed?

**Not yet.** The code infrastructure was built correctly in worktree isolation, but:

- ✅ Schema partially updated (8/14 fields)
- ✅ empirical.py partially updated (metric extraction, not MHT)
- ✅ walk_forward_validate() on main
- ✅ run_summary.py on main
- ✅ 93 new tests across 3 test files (all pass)
- ❌ **mht.py missing from main** (BLOCKING)
- ❌ **No rerun conducted**
- ❌ **No centralized summary generated**

---

## Was Any Promising Alpha Candidate Found?

**No.** All 6 canonical reports show `oos_trade_count=0`, which means no candidate was evaluated with correct metrics. The reports cannot be used to determine whether any alpha signal exists.

---

## Next Recommended Issue

**Step 1: Fix v0.25 sync gaps (immediate)**

1. Commit `mht.py` from worktree-9 to main
2. Commit `test_mht.py` from worktree-9 to main
3. Restore `test_schema_active_metrics.py` (recover from git history or worktree-9)
4. Complete schema with 6 missing fields
5. Update `empirical.py` MHT code to use `trial_context`
6. Run full test suite: `python3 -m pytest alphaforge/tests/ contracts/tests/ lib/tests/ integration/tests/ -q`

**Step 2: Rerun discovery (same config, same symbols, same parameters)**

```bash
python3 cli/real_training.py --mode SWING --symbols BTCUSDT,ETHUSDT,SOLUSDT
python3 cli/real_training.py --mode SCALP --symbols BTCUSDT,ETHUSDT,SOLUSDT
python3 cli/real_training.py --mode AGGRESSIVE_SCALP --symbols BTCUSDT,ETHUSDT,SOLUSDT
```

**Step 3: Generate centralized summary**

```bash
python3 cli/generate_run_summary.py --report-dir data/reports --output data/reports/research_run_summary.json
```

**Step 4: Analyze new reports**

Compare new vs old: 
- oos_trade_count > 0?
- active_trade_count present?
- fold_count = 6?
- MHT correction applied?
- Root cause tree accurate?

---

## What NOT to Do Next

| Do Not Do | Why |
|-----------|-----|
| Do NOT start #115 Cost Stress Matrix | Diagnostic layer incomplete — baseline metrics would be unreliable |
| Do NOT start #116 Symbol/Regime Stability | Same reason |
| Do NOT start #117 NO_TRADE Collapse | Same |
| Do NOT start #118 Autotune | Premature without verified diagnostics |
| Do NOT start #119 Alpha Surface Expansion | Cannot evaluate new surfaces |
| Do NOT generate new candidates | Diagnostic engine not verified |
| Do NOT claim v0.25 complete | Until mht.py is on main and rerun passes |

---

## Readiness Scores

| Dimension | Score | Interpretation |
|-----------|-------|---------------|
| Diagnostic Engine Readiness | **35%** | Code partially on main, MHT missing, no verified rerun |
| Alpha Candidate Readiness | **10%** | No candidate evaluated with correct metrics |
| Autotune Readiness | **5%** | Missing: verified metrics, MHT, cost stress, no-trade collapse |
| V7 Promotion Readiness | **0%** | No gate-ready evidence exists |

---

## Workflow Sync Root Cause

```
Workflow created agents in isolated worktrees
  → Agent 9 (MHT) created mht.py + test_mht.py
  → Files were NOT git add/committed in worktree
  → sync-worktrees.sh only cherry-picks COMMITTED changes
  → mht.py left behind as untracked file
  → test_schema_active_metrics.py committed in sync #1
    → then DELETED in sync #2 (sync script copied state without it)
```

This is a known pattern with worktree isolation: if agent scripts don't explicitly `git add` and `git commit` new files, the sync step misses them. The fix is to either:
- (a) Ensure each workflow agent commits its files before completing
- (b) Use a sync script that also copies untracked files (not cherry-pick only)
- (c) Manually commit mht.py from worktree-9

---

*Analysis generated in read-only mode. No implementation, training, or network calls performed.*
*This is a diagnostic assessment, NOT an alpha discovery or promotion statement.*
