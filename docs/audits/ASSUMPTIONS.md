# V7 Engine — Assumptions Register

> **Status:** ACTIVE
> **Purpose:** Documents explicit assumptions with confidence levels and evidence.
> When an assumption is verified, it graduates to `FINDINGS_LEDGER.md`.
> When disproved, it moves to `OPEN_QUESTIONS.md` with the contradiction evidence.

---

## A-001 — Domain Import Boundaries Are Correct and Complete

**Confidence:** 0.95
**Last verified:** 2026-07-11
**Verification method:** CI boundary tests pass

**Statement:** The domain ownership and import rules defined in `governance.md` and enforced by `integration/tests/test_cross_domain_boundaries.py` correctly capture all forbidden dependency paths.

**Risk if wrong:** A latent circular import or forbidden dependency could create subtle bugs when new code is added.

**Evidence:** 96 boundary tests pass. Multiple pre-existing violations were caught and fixed during P0–P6.

---

## A-002 — Training Config Defaults Are Safe Starting Points

**Confidence:** 0.80
**Last verified:** 2026-07-11
**Verification method:** Research training run on real data

**Statement:** The default training hyperparameters (lr=0.1, depth=4, subsample=0.9, class weights) produce reasonable results for exploration but are not production-optimized.

**Risk if wrong:** Using unoptimized defaults in production could lead to poor risk-adjusted returns.

**Evidence:** F-007: IC=0.2387, ECE=0.0922 on 10-symbol run. Reasonable but not validated for production.

---

## A-003 — SWING Mode Profile Is Architecturally Correct

**Confidence:** 0.85
**Last verified:** 2026-07-10
**Verification method:** Code review + design lock audit

**Statement:** SWING mode simulation profile semantics (horizon, stop/target multipliers, position sizing) correctly implement the business requirements for a swing trading mode.

**Risk if wrong:** Profile errors would corrupt SWING simulation results and mislead policy decisions.

**Evidence:** F-010: thresholds are LOCKED_INITIAL_BASELINE, not empirically validated.

---

## A-004 — ETH/BNB/SOL Data Is Representative of Market Conditions

**Confidence:** 0.90
**Last verified:** 2026-07-06
**Verification method:** Dataset audit — 29,928 rows, 0 NaN, 0 gaps, 0 duplicates

**Statement:** The three cleanest symbols (ETH, BNB, SOL) provide representative market conditions for training and evaluation. Behavior on these symbols generalizes to other major pairs.

**Risk if wrong:** Models trained only on clean symbols may not generalize to noisier pairs or altcoins.

**Evidence:** F-003: ETH/BNB/SOL are perfectly clean. F-016: research run included 10 symbols successfully.

---

## A-005 — Binance Fee Structure Is Stable

**Confidence:** 0.95
**Last verified:** 2026-07-10
**Verification method:** Historical fee schedule review

**Statement:** The 0.02% maker / 0.05% taker fee tier used in simulation costs will remain representative for the foreseeable future. Fee changes by Binance would require cost model update.

**Risk if wrong:** Fee changes would systematically bias simulation P&L.

**Evidence:** Current Binance fee schedule for standard VIP levels.

---

## A-006 — Single-Thread Preprocessing Is the Current Limiting Factor

**Confidence:** 0.94
**Last verified:** 2026-07-11
**Verification method:** Profiling (F-009)

**Statement:** The CPU-bound single-threaded preprocessing loop is the primary performance bottleneck for scaling training beyond 10 symbols.

**Risk if wrong:** Optimizing preprocessing would not yield material speedup if GPU compute or I/O is the real bottleneck.

**Evidence:** F-009: 68% pre-training overhead, 96% CPU on one core, <4% GPU.

---

## A-007 — All Tests Pass Consistently Across Environments

**Confidence:** 0.90
**Last verified:** 2026-07-11
**Verification method:** CI + local runs

**Statement:** The test suite is deterministic and environment-independent modulo the 1 pre-existing CLI failure (F-014) and 22 expected skips (F-008).

**Risk if wrong:** Environmental differences (Python version, OS, hardware) could introduce non-deterministic failures.

**Evidence:** Multiple verification runs on different machines produce identical results.

---

## A-008 — ACCP-YAML Is Sufficient for Machine-Readable Auditing

**Confidence:** 0.85
**Last verified:** 2026-07-11
**Verification method:** Cross-referencing ACCP reports against code changes

**Statement:** The ACCP-YAML format captures all necessary task completion evidence for independent verification.

**Risk if wrong:** Missing fields or unstructured evidence would force manual re-audit.

**Evidence:** 40+ ACCP reports in `reports/`. All structured with `result`, `files_changed`, `decisions_locked`, `evidence`.

---

## A-009 — Agent Context Files (This System) Are Read by Workers

**Confidence:** 0.95
**Last verified:** 2026-07-11
**Verification method:** Protocol definition

**Statement:** All AI workers entering this repository will read `.agent/CONTEXT_INDEX.md` and follow the defined reading order before starting work.

**Risk if wrong:** Workers would operate with stale or incomplete context, repeating past work or contradicting locked decisions.
