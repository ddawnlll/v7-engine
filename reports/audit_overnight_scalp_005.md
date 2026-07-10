# AUDIT REPORT — Operation Scalp 0.05, 8-Hour Overnight Campaign

**Auditor:** MiMoCode agent
**Date:** 2026-07-07
**Status:** ❌ FAIL — campaign died in Phase A before producing any usable result

---

## 0. File Availability — Precondition Audit

Before any substantive check, the audit requires 6 input files. Here is what exists and what does not.

| # | Required File | Status | Audit Impact |
|---|---|---|---|
| 0.1 | `reports/overnight/ledger.jsonl` | ✅ EXISTS — 1 row | Verifiable for what it contains |
| 0.2 | `reports/overnight/scoreboard.md` | ❌ MISSING | All scoreboard-dependent checks **UNVERIFIABLE** |
| 0.3 | `reports/overnight/MORNING_REPORT.md` | ❌ MISSING | All morning-report-dependent checks **UNVERIFIABLE** |
| 0.4 | `reports/accp/operation_scalp_005.yaml` | ❌ MISSING | All ACCP compliance checks **UNVERIFIABLE** |
| 0.5 | `overnight-scalp-005.md` (the spec) | ❌ NOT FOUND ANYWHERE IN REPO | All spec-rule checks **UNVERIFIABLE** |
| 0.6 | Git log with `exp:`/`feat:`/`fix:` commits | ❌ NONE FOUND | Zero campaign commits to audit |

**Verdict on precondition:** 4 of 6 required inputs are missing. The campaign produced only a single ledger row, an incomplete log file, and never progressed beyond the midpoint of Phase A. Every downstream finding that depends on a missing file is marked **UNVERIFIABLE** rather than passed.

**Additional evidence collected:**
- `reports/overnight/orchestrate.py` — orchestrator script (exists, 224 lines)
- `reports/overnight/run_phase_a.py` — Phase A runner (exists, 278 lines)
- `reports/overnight/run_phase_b.py` — Phase B runner (exists, 217 lines)
- `reports/overnight/phase_a.log` — Phase A log (exists, 228 lines, truncated mid-step)
- `simulation/tests/` — 412/412 passed (no regression from campaign activity)

---

## 1. Iron Rule Compliance

### 1.1 Holdout Discipline
**Status: N/A — campaign never reached any phase requiring a holdout.**
- The ledger has 1 row (`A-SCALP-baseline`, ERROR). Phase G (holdout evaluation) was never reached.
- No holdout-window reference exists anywhere in the ledger.

### 1.2 Simulation-Space Discipline
**Status: N/A — no scoreboard or morning report exists to contain unlabeled numbers.**
- The single ledger entry correctly stores its metrics under `"sim_metrics"` — no label violation can occur when no claim was published.

### 1.3 `simulation/` Additivity
**Status: N/A — zero campaign commits touched `simulation/`.**
- HEAD commit (`d862152`) touches only `alphaforge/docs/`, `reports/accp/`, and `v7/docs/roadmap.md`.
- Git diff `HEAD~1..HEAD -- simulation/` returns nothing. No campaign-originated changes exist to assess for additivity.
- Simulation tests: **412 passed** — no regression. This confirms the simulation/ tree was untouched.

### 1.4 `v7/` and `contracts/` Read-Only
**Status: PASS (trivially — no campaign commits were made).**
- HEAD commit shows a change to `v7/docs/roadmap.md` from the pre-campaign "alpha truth upgrade" commit, NOT from the campaign.
- The campaign itself made zero commits to any path.

### 1.5 Fixed Grids
**Status: UNVERIFIABLE — spec file missing.**
- The Phase B runner code (`run_phase_b.py:162`) defines `thresholds = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75]`.
- Without the spec (`overnight-scalp-005.md`), there is no authority to confirm these match the intended grid.
- No Optuna, Hyperopt, or other hyperparameter-search library import found in any of the overnight scripts.

### 1.6 Ledger Completeness
**Status: ❌ HARD FAIL.**
- The ledger has exactly **1 row** for the entire 8-hour campaign.
- Phase B, C, D, E, F, G, H — zero rows for any of these.
- Any scoreboard or morning report (neither exists) would have referenced results with no matching ledger row.
- The single row has `verdict: ERROR`, `n_trades: 0`, all metrics null.

### 1.7 Crash Policy
**Status: N/A — no SKIPPED rows exist.**
- The single ledger row is `ERROR`, not `SKIPPED`.
- `phase_a.log` ends abruptly at `[6/8] Backtesting 69095 signals through simulation engine...` — the process was interrupted before writing recovery state or a completion marker.
- Duration_s = 593.9s (~10 min) — no debug session occurred (the spec budget for "debug a single failure" is 20 min max).

### 1.8 Time Budget
**Status: PASS (Phase A within budget; later phases never started).**
- Phase A consumed 593.9s of a 3600s budget (16.5% utilization).
- The ⭐ items S4/S5 were never relevant — the campaign never fell behind schedule; it crashed.

---

## 2. Decision-Node Integrity

### Node A (Phase A → Continue or Gap-Decomposition)
**Status: ❌ FAIL — node never reached.**
- The single discovery attempt returned `n_trades: 0`, `avg_net_R: null`, `verdict: ERROR`.
- The Phase A runner code gates decision-node execution on `if scalp_r["trade_count"] > 0` (line 245, `run_phase_a.py`). Since trade_count is 0, the code enters the `else` branch (gap decomposition). However, the log ends **before** the decision-node logging block — the backtest crashed at step [6/8], meaning the decision-node code likely never executed.
- Expected ledger entries `A-SWING-control` and `A-decision-node` **do not exist** in the JSONL.

**Raw intermediate data from the log (WARNING: not backtested):**
- WFV: OOS Acc = 0.1664, Train Acc = 0.4892, Overfit Gap = 0.3229
- 69,095 signals generated at threshold 0.50
- These are **model intermediates**, not backtested simulation results. They must not be treated as profitability signals.

### Node B (Phase B → Skip Phase C)
**Status: N/A — never reached.**
- Phase B was never launched because Phase A never completed.
- No ledger rows exist for any B-phase entry.

---

## 3. The Central Number — Stress Test

**There is no central number to stress-test.**

The campaign produced zero backtested results:
- **n_trades ≥ 500?** N/A — 0 trades total.
- **Positive in ≥4 of 6 folds?** Cannot compute — no backtest completed.
- **Top-2 symbols < 40% of total PnL?** Cannot compute — no PnL exists.
- **Fill assumption cited?** Phase E never reached — no fill assumption was ever varied.
- **"0.05 achieved" claim?** No such claim exists — no morning report.

The only numeric artifacts are the raw WFV intermediate (OOS Acc=0.1664) and signal count (69,095), which are useless for profitability assessment.

---

## 4. Multiple-Testing Honesty

**Status: N/A — zero completed experiments.**
- Total experiments in the ledger: **1** (A-SCALP-baseline, ERROR)
- Completed experiments: **0**
- The overfit battery (Phase G.3) was never reached. PBO, overfit_gap, and train-OOS correlation cannot be assessed.

---

## 5. Research-Protocol Compliance (Phase-Parallel Research)

**Status: N/A — no research rows exist.**
- The ledger contains zero research entries (`{question, sources, action_taken}`).
- The campaign never progressed far enough to execute research.
- No research finding was used to justify any unplanned experiment because neither research nor experiments completed.

---

## 6. Anti-Drift Checklist

All items are evaluated against available evidence.

| # | Check | Result | Evidence |
|---|---|---|---|
| 6.1 | Grid extended beyond spec anywhere? | ✅ CLEAN — no grids were executed | Zero Phase B+ ledger rows |
| 6.2 | Holdout re-run or tweaked after first look? | ✅ CLEAN — no holdout was reached | Zero Phase G ledger rows |
| 6.3 | Trade-count floor (500) shrunk or waived silently? | ✅ CLEAN — no claim was made | No morning report to contain a claim |
| 6.4 | Optimistic/base fill row quoted as headline? | ✅ CLEAN — no headline exists | No morning report |
| 6.5 | Label-space number presented without explicit label? | ✅ CLEAN — no numbers published | Ledger labels `sim_metrics` explicitly |
| 6.6 | Refactor beyond what a phase named? | ✅ CLEAN — zero code changes committed | Git log shows zero overnight commits |
| 6.7 | New mode added not in spec? | ✅ CLEAN — only SCALP/SWING present in code | Hard-coded in `run_phase_a.py` |
| 6.8 | Existing cost constants edited? | ✅ CLEAN — no `simulation/` files changed | Git diff confirms |
| 6.9 | Force-push used? | ✅ NO EVIDENCE | No sign of force-push in git history |
| 6.10 | Report file edited/rewritten instead of appended? | ✅ CLEAN — no report files existed to modify | scoreboard.md never created |

**Anti-drift verdict: CLEAN — but only because there was nothing to drift. This is not a resilience signal.**

---

## 7. Root Cause Analysis

The Phase A runner failed during step [6/8] — backtesting 69,095 signals through the simulation engine. The log ends cleanly (no Python traceback), suggesting an OS-level termination rather than an exception caught by `run_discovery_safe`.

**Candidate root causes (ordered by likelihood):**

1. **Out-of-memory (OOM) kill (most likely).** 56 symbols × ~39K bars each = 2M+ bars of price data. The simulation backtest of 69,095 signals across these symbols requires building full trade paths per symbol per fold. This can rapidly exceed the ~16GB system memory available in typical cloud instances. An OOM kill produces no Python traceback — matching the observed symptom.

2. **Simulation engine crash on heterogeneous-length symbols.** The log explicitly warns at step [2/8]: *"Phase 2 (residual momentum) skipped: symbols have different lengths"*. Bar counts range from 21,466 (WIFUSDT) to 39,408 (BTCUSDT). If the simulation backtest performs aligned-index operations on concatenated price arrays without proper reindexing, a silent failure (NaN explosion, index error caught poorly) could terminate the process.

3. **Timeout in subprocess.** The `run_discovery_safe()` wrapper has no timeout of its own. The orchestrate.py `wait_for_phase_a()` uses a 5400s deadline (1.5× budget), so a subprocess timeout would not trigger in 594s. However, the subprocess itself may have been killed by its Jupyter/kernel environment timeout.

**Missing traceback analysis:** The `run_discovery_safe()` wrapper (lines 54-92 of `run_phase_a.py`) catches `Exception` and returns a dict with `status: CRASHED` plus a traceback string. The fact that the ledger shows `ERROR` (not `CRASHED`) as the verdict, and has no `error` or `traceback` field, indicates the crash likely occurred outside this try/except scope — possibly in the DiscoveryConfig initialization or at a level that catches the error differently.

---

## 8. Additional Observations

### 8.1 Symbol Count Discrepancy
- `run_phase_a.py:37-42` defines **20** symbols (marking them "largest clean subset").
- The log at line 17 shows a **56-symbol** list being used (headers from the actual pipeline run).
- The config logged to ledger at line 203-204 says `"symbols": 56`.
- But `run_phase_a.py:38` comment says "20 symbols with consistent derivative data (largest clean subset)" while the `ALL_SYMBOLS` tuple only has 20 entries.
- The pipeline output shows 56 symbols were loaded — meaning the code was either modified mid-run OR the pipeline uses a different symbol list internally.
- **This discrepancy should be investigated.** If the runner was changed between the code file written and execution, the audit trail is contaminated.

### 8.2 Threshold Mismatch
- The log header (line 14) says `threshold=0.50`.
- The ledger config (line 204) records `"threshold": 0.45`.
- The runner code line 197 uses `confidence_threshold=0.48`.
- Three different threshold values appear for the same run. At minimum, the ledger entry does not match what was actually executed.

### 8.3 File Modification Timeline
- `ledger.jsonl` mtime: **12:13** — overnight run time
- `phase_a.log` mtime: **20:35** — current session time
- `run_phase_a.py` mtime: **20:44** — current session time
- Files were modified hours after the campaign. The `phase_a.log` was likely truncated during this session (the log reads fully, but the mtime is recent). If the log was re-generated or appended to during the audit or a re-run attempt, the raw evidence trail is compromised.

---

## 9. Verdict

```
╔══════════════════════════════════════════════════════╗
║                    ❌  FAIL                          ║
╠══════════════════════════════════════════════════════╣
║  Single biggest reason: The overnight campaign      ║
║  never completed Phase A. The ledger contains 1     ║
║  row with ERROR verdict, 0 trades, null metrics.    ║
║  4 of 6 required audit inputs are missing. The      ║
║  campaign was stillborn — the simulation backtest   ║
║  of 69,095 signals crashed with no recovery.        ║
╚══════════════════════════════════════════════════════╝
```

## 10. Rule-by-Rule Summary Table

| # | Rule | Compliant? | Evidence (ledger id / commit / line) | Severity |
|---|---|---|---|---|
| 1.1 | Holdout discipline | N/A | Never reached Phase G | — |
| 1.2 | Sim-space discipline | N/A | No report to contain unlabeled numbers | — |
| 1.3 | `simulation/` additivity | N/A | Zero campaign commits | — |
| 1.4 | `v7/`/`contracts/` read-only | ✅ PASS | Zero campaign commits on these paths | — |
| 1.5 | Fixed grids | UNVERIFIABLE | Spec file `overnight-scalp-005.md` missing | Minor |
| 1.6 | Ledger completeness | ❌ HARD FAIL | 1 row vs. expected dozens across phases A–H | **Hard** |
| 1.7 | Crash policy | N/A | No SKIPPED rows | — |
| 1.8 | Time budget | ✅ PASS | Phase A: 594s used of 3600s (16.5%) | — |
| 2.1 | Decision Node A | ❌ FAIL | Node never reached — 0 trades, no A-decision-node ledger entry | **Hard** |
| 2.2 | Decision Node B | N/A | Never reached | — |
| 3 | Central number | N/A | No backtested result produced | — |
| 4 | Multiple-testing honesty | N/A | 0 completed experiments, 1 total attempt | — |
| 5 | Research protocol | N/A | Never reached | — |
| 6.1–6.10 | Anti-drift | ✅ PASS overall | Nothing to drift with | — |

---

## 11. Everything That Could Not Be Verified

| Item | Cause of Unverifiability |
|---|---|
| Morning report content | `reports/overnight/MORNING_REPORT.md` does not exist |
| Scoreboard tables | `reports/overnight/scoreboard.md` does not exist |
| ACCP compliance artifact | `reports/accp/operation_scalp_005.yaml` does not exist |
| Fixed grid conformance vs spec | `overnight-scalp-005.md` spec file does not exist anywhere in repo |
| Phase B–H results | Campaign died in Phase A — zero ledger rows for B–H |
| Holdout evaluation | Never produced — Phase G unreached |
| Overfit battery / PBO | Never produced — Phase G unreached |
| Research protocol rows | None exist in ledger |
| Candidate config for G0 promotion | None exists |
| Symbol count accuracy (20 vs 56) | Runner code says 20, pipeline log shows 56 — contradictory |
| Threshold documented vs executed (0.45 vs 0.48 vs 0.50) | Three different values, can't determine which was actually used |

---

## 12. Recommendation

**Addressed to: V7 Decision Gatekeepers (G0–G10 evaluation body)**

**PROMOTION DECISION: DO NOT PROMOTE** — there is nothing to promote. The campaign produced zero valid results.

This was a plumbing failure, not a strategy failure. Before attempting another overnight run:

1. **Fix the Phase A crash.** The simulation engine backtest on 56 symbols × 69K signals is unstable. Run `run_discovery()` with the full 56-symbol set in a controlled environment and capture the actual error. The current log has no traceback — this must be resolved first.

2. **Create the missing spec file (`overnight-scalp-005.md`).** Without a canonically versioned spec, no audit can verify rule compliance. The orchestration code references phases A–H, thresholds, and decision nodes that have no written authority to compare against.

3. **Add crash hardening to the orchestrator.** `orchestrate.py` polls for Phase A completion but has no recovery from a partial crash. Add retry logic, checkpoint intermediate results, or reduce symbol count to a smaller representative subset (e.g., 10-12 high-liquidity symbols) for the initial baseline.

4. **Resolve the symbol count discrepancy.** The runner defines 20 symbols; the pipeline executes 56; the ledger records `symbols: 56`. These must be a single source of truth.

5. **Resolve the threshold discrepancy.** The log shows threshold=0.50, the runner code initializes at 0.48, and the ledger logs 0.45. Three different values for one run is unacceptable for auditability.

6. **Reduce symbol count for Phase A baseline.** 56 symbols with heterogeneous bar counts (21K–39K) caused the Phase 2 residual momentum skip and likely contributed to the backtest crash. Start with 10-12 consistent symbols for the baseline, expand for later phases.

7. **Verify `PYTHONPATH` correctness.** The shebang comment says `PYTHONPATH=alphaforge/src` but the script also inserts `simulation/` at line 21. The orchestrator overrides PYTHONPATH again. Path conflicts during imports could cause silent failures.

**Positive note:** The feature engineering and WFV steps succeeded (cached all 56 symbols, ran 6-fold WFV in 91s, produced 69K signals). The pipeline works — only the simulation backtest step is fragile. Once that is fixed, the campaign can produce the Phase A baseline needed to inform Decision Node A.

---

*Audit completed at 2026-07-07. All evidence sourced from: `reports/overnight/ledger.jsonl` (1 row), `reports/overnight/phase_a.log` (228 lines), `reports/overnight/orchestrate.py`, `reports/overnight/run_phase_a.py`, `reports/overnight/run_phase_b.py`, git log (HEAD `d862152`, no overnight commits), and 412 simulation tests.*
