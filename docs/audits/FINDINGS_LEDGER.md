# V7 Engine — Audit Findings Ledger

> **Status:** ACTIVE
> **Purpose:** All verified audit findings in a single machine-readable ledger.
> Each finding has a unique ID (F-NNN), severity, confidence score, and evidence.
>
> **Rules:**
> - New findings are appended by worker agents at task completion.
> - Existing findings are updated when new evidence changes confidence.
> - Contradictions must be recorded as separate findings pointing to the original.
>
> **Format:**
> ```
> ## F-NNN — Title
> Status: CONFIRMED / REVISED / SUPERSEDED / DISPROVED
> Severity: CRITICAL / HIGH / MEDIUM / LOW / INFO
> Confidence: 0.00–1.00
> ```

---

## F-001 — AlphaForge Pipeline P1–P9 Complete

**Status:** CONFIRMED
**Severity:** INFO
**Confidence:** 1.00
**Scope:** alphaforge/src/alphaforge/
**Discovered by:** Wave 0 verification
**Validated by:** Full test suite

**Description:** AlphaForge end-to-end pipeline (label builder → dataset assembly → XGBoost training → calibration → evaluation → monitoring) is implemented and tested.

**Evidence:**
- `train_pipeline.py` runs end-to-end on 10 symbols × 2000 bars
- Training duration: 0.61s (SCALP mode)
- 112 passing tests in alphaforge/tests/
- P1–P9 phases marked complete in roadmap

---

## F-002 — Test Suite: 847 Tests, 95.5% Pass Rate

**Status:** CONFIRMED
**Severity:** INFO
**Confidence:** 1.00
**Scope:** Entire repo
**Discovered by:** CI pipeline
**Validated by:** Multiple verification runs

**Description:** Full test suite runs clean. 1 pre-existing failure in CLI tests (alphaforge.features module path).

**Evidence:**
- `verify_summary.md` SHA: `be758454c73f681138f11f659c702ed072c3b3c0`
- Breakdown: lib=182, simulation=73, integration=96, runtime=374, alphaforge=112, v7=6, policycritic=7
- 22 xfailed (expected: funding real-data scenarios)

---

## F-003 — BTCUSDT Data Has Duplicates and 59-Day Gap

**Status:** CONFIRMED
**Severity:** HIGH
**Confidence:** 1.00
**Scope:** `data/raw/BTCUSDT/`
**Discovered by:** AlphaForge Dataset Auditor
**Validated by:** Independent parquet inspection

**Description:** BTCUSDT has 4 duplicate rows and a 59-day gap (Jan 2 – Mar 1 2024). Other symbols (ETH, BNB, SOL) are clean.

**Finding ID:** DEC-008
**Impact:** Training windows spanning Q1 2024 get BTC data from 28,492 rows instead of 29,928. NaN propagation into cache panels.

**Evidence:**
- Duplicate timestamps: 1704067200000 (x2), 1704153600000 (x2)
- BTC rows: 28,492 vs expected 29,928 (1,438 missing)
- ETH/BNB/SOL rows: 29,928, no gaps/dupes

---

## F-004 — Cache Factor Panels Have 7.35% NaN Rate

**Status:** CONFIRMED
**Severity:** MEDIUM
**Confidence:** 0.95
**Scope:** `cache/factor_sprint/`
**Discovered by:** AlphaForge Dataset Auditor
**Validated by:** NaN counting across 7 symbols

**Description:** 5 cache panels have 43,989 NaN cells. Delisted/getting-listed symbols dominate.

**Breakdown:**

| Symbol | NaN Count | NaN % |
|--------|-----------|-------|
| MATICUSDT | 15,062 | 50.33% |
| BTCUSDT | 6,528 | 21.81% |
| BNBUSDT | 5,832 | 19.50% |
| ETHUSDT | 5,832 | 19.50% |
| SOLUSDT | 5,832 | 19.50% |
| SUIUSDT | 2,944 | 9.84% |
| ARBUSDT | 1,959 | 6.55% |

**Impact:** XGBoost handles NaN natively, but high NaN rates for delisted symbols may distort training if not masked.

**Evidence:**
- Panel file: `cache/factor_sprint/panel_d8c8d55e3b8b107e_close.parquet`
- MATIC 50.33% NaN → delisted symbol, should be excluded
- BTC NaN correlated with raw data gap (F-003)

---

## F-005 — Candidates Dataset Is Clean (10,000 rows, 0 NaN)

**Status:** CONFIRMED
**Severity:** INFO
**Confidence:** 1.00
**Scope:** `data/candidates/outcomes_v1.parquet`
**Discovered by:** AlphaForge Dataset Auditor
**Validated by:** parquet inspection

**Description:** The training candidates dataset is contiguous, no NaN, no Inf, no duplicates, consistent 1h intervals.

**Evidence:**
- 10,000 rows, 0 NaN, 0 Inf, 0 gaps
- Contiguous 1-hour intervals
- Clean across all columns

---

## F-006 — Simulation Outcome Columns Are Correctly Forward-Looking

**Status:** CONFIRMED
**Severity:** LOW
**Confidence:** 1.00
**Scope:** data/candidates/outcomes_v1.parquet
**Discovered by:** AlphaForge Dataset Auditor
**Validated by:** Independent review

**Description:** `net_R`, `gross_R`, `mfe_R`, `mae_R`, `exit_reason`, `hold_duration` columns in candidates datasets are simulation outputs stored as labels/targets. This is correct usage, NOT lookahead bias. Training code must still be verified to not use these as features.

**Evidence:**
- Column names contain no suspicious lookahead patterns
- These are simulation outputs, not future data
- Training code audit deferred to separate task

---

## F-007 — SCALP Training: IC=0.2387, ECE=0.0922 on Real Data

**Status:** CONFIRMED
**Severity:** INFO
**Confidence:** 0.90
**Scope:** alphaforge training pipeline
**Discovered by:** Research training run
**Validated by:** 10-symbol × 2000-bar real data run

**Description:** SCALP XGBoost model on 10 symbols with 16 features shows positive signal detection with reasonable calibration.

**Training profile:**
- lr=0.1, depth=4, subsample=0.9
- Class counts: LONG_NOW=3600, SHORT_NOW=3600, NO_TRADE=8800
- Weights: NO_TRADE=1.0, LONG_NOW=2.44, SHORT_NOW=2.44
- Val accuracy: 0.3377, Val logloss: 1.0982

**Results:**
- IC=0.2387 ✅ Positive signal
- RankIC=0.2254
- ECE=0.0922 ✅ Reasonable calibration
- MCE=0.4733
- WFV 6-fold avg accuracy: 0.4480

**Evidence:**
- `reports/research_run_real_10sym.json`
- `scripts/real_research_run.py`

---

## F-008 — Wave 0 Acceptance: 24 Passed, 22 XFailed

**Status:** CONFIRMED
**Severity:** INFO
**Confidence:** 1.00
**Scope:** Integration tests
**Discovered by:** Wave 0 verification
**Validated by:** CI

**Description:** Acceptance tests for funding costs (#267, #304, #315) and row identity pass. 22 xfailed are expected — they require real Binance data that can't be fetched in CI.

**Evidence:**
- `verify_summary.md`
- 24 passed, 22 xfailed
- Test files: `test_funding_costs.py`, profile registry tests

---

## F-009 — Training Pipeline 68% Pre-Training Overhead

**Status:** CONFIRMED
**Severity:** HIGH
**Confidence:** 0.94
**Scope:** `alphaforge/data/preprocessing.py` (lines 118-201), `training/pipeline.py`
**Discovered by:** GPT-5.6 audit (offline)
**Validated by:** DeepSeek V4 worker profiling

**Description:** 68% of total training pipeline duration is spent on dataset preprocessing before training begins. The preprocessing loop is single-threaded and CPU-bound.

**Evidence:**
- `profiling/*.json` — stage-level duration data
- CPU utilization: 96% on one core
- GPU utilization: below 4%
- Single-threaded loop in `preprocessing.py:118-201`

**Impact:** Scaling to more symbols or higher frequency compounds this overhead linearly.

**Decision (DEC-006):** Do NOT blindly port entire pipeline to CUDA. Benchmark each stage independently. Test multiprocessing/DataLoader workers. Identify transforms suitable for torch/CUDA.

---

## F-010 — SWING Mode Thresholds Unvalidated

**Status:** CONFIRMED
**Severity:** MEDIUM
**Confidence:** 0.85
**Scope:** Simulation profiles for SWING mode
**Discovered by:** design lock audit
**Validated by:** Independent review

**Description:** SWING mode simulation profiles (stop/target multipliers, position sizing) have been set to conservative defaults but NOT empirically validated against real data. These are marked as `LOCKED_INITIAL_BASELINE` — meaning they're safe starting points, not proven optimal.

**Evidence:**
- `simulation/docs/profiles.md`
- SWING thresholds in profile configs
- No real-data backtest results for SWING specifically yet

---

## F-011 — Runtime Safety Gates Implemented and Tested

**Status:** CONFIRMED
**Severity:** INFO
**Confidence:** 1.00
**Scope:** `runtime/runtime/safety/`
**Discovered by:** Wave 1 implementation
**Validated by:** 52 passing safety tests

**Description:** Circuit breaker, max drawdown, position concentration, and rate limit gates are implemented and tested. Shadow harness architecture in place.

**Evidence:**
- `runtime/tests/test_safety_rails.py` — 52 tests
- `reports/issue288_safety_rails_shadow_harness.accp.yaml`

---

## F-012 — Policy Critic RL Research (P10) In Progress

**Status:** CONFIRMED
**Severity:** INFO
**Confidence:** 0.70
**Scope:** `policycritic/`, `v7/docs/policy_critic/`
**Discovered by:** Roadmap review
**Validated by:** Policy Critic ai_summary exists

**Description:** Offline IQL-based advisory RL component is in research phase. Design docs, business plan, and codebase maps exist but implementation is not complete (7 tests only).

**Evidence:**
- `v7/docs/policy_critic/ai_summary.md`
- 7 tests in policycritic/tests/
- Multiple ACCP reports in reports/ directory

---

## F-013 — Interface (React UI) Rebuild In Progress

**Status:** CONFIRMED
**Severity:** LOW
**Confidence:** 0.80
**Scope:** `interface/`
**Discovered by:** Project audit
**Validated by:** Interface docs

**Description:** The operator UI is being rebuilt with a new information architecture. Current state has both old and new components. Migration plan documented.

**Evidence:**
- `interface/docs/ai_summary.md`
- New IA blueprint exists
- Old components still present

---

## F-014 — CLI Tests Have 1 Pre-Existing Failure

**Status:** CONFIRMED
**Severity:** LOW
**Confidence:** 1.00
**Scope:** `cli/tests/`
**Discovered by:** Multiple test runs
**Validated by:** CI + local runs

**Description:** 1 test consistently fails due to alphaforge.features module path issue. Root cause not yet fixed. Does not affect core pipeline or safety.

**Evidence:**
- All verify_summary.md runs show this
- `cli/tests/: 61 passed, 1 failed`

---

## F-015 — Profiling Data Exists But Not In Standard Format

**Status:** CONFIRMED
**Severity:** LOW
**Confidence:** 0.90
**Scope:** `reports/`, profiling data
**Discovered by:** Audit memory layer setup
**Validated by:** File inspection

**Description:** Multiple profiling/pipeline timing JSON files exist but with inconsistent schemas, making cross-run comparison difficult.

**Files found:**
- `pipeline_profile.json`, `pipeline_profile_detailed.json`
- `pipeline_profile_final.json`, `pipeline_profile_optimized.json`
- `pipeline_profile_real_data.json`

---

## F-017 — Volume Specialist Is a Research Candidate, Not a Promotion Candidate

**Status:** CONFIRMED
**Severity:** INFO
**Confidence:** 1.00
**Scope:** `alphaforge.train` / SCALP 1h factor-sprint panel
**Validated by:** Canonical timestamp-aware 6-fold WFV on 10 symbols, 276,566 samples

**Description:** The isolated `volume` feature family with cross-sectional rank
normalization disabled produced `+0.012715R` per active trade, 14,308 active
trades (12.22% exposure), and positive R in all six folds. This remains **HOLD**:
the OOS/train gap is `0.2498` and PBO is `HIGH`; it must not be sent to V7-lite
or execution without untouched holdout and cost-stress evidence.

**Evidence:** Remote canonical run `/tmp/af_specialist_volume_no_rank_audited.json`
on 2026-07-13; fold R `0.007711, 0.014512, 0.010832, 0.017033, 0.009801, 0.011771`.

**Follow-up validation (2026-07-13):** A model fitted only before
`2026-01-01` produced `+0.009417R` on the 36,110-sample 2026 holdout; it
remained positive at 1.5x (`+0.009017R`) and 2.0x (`+0.008617R`) round-trip
cost. A development-only nested threshold sweep selected 0.70, but that
threshold yielded only 37 holdout trades (0.1% exposure). The alpha candidate
is confirmed; its production threshold remains HOLD.

---

## F-016 — Real Data Research Run Successful (10 Symbols)

**Status:** CONFIRMED
**Severity:** INFO
**Confidence:** 1.00
**Scope:** Training pipeline
**Discovered by:** `scripts/real_research_run.py`
**Validated by:** SHA-verified parquet files

**Description:** Cross-symbol research training run completed successfully on real Binance data. 10 symbols × 2000 bars used.

**Symbols:** BTC, ETH, BNB, SOL, XRP, ADA, DOGE, AVAX, DOT, LINK
**Evidence:**
- `reports/research_run_real_10sym.json`
- `data/raw/*/*.parquet.sha256` — provenance verified

---

## F-018 — Interval-Aware Fresh Replay Requires Same-Symbol Exclusivity

**Status:** CONFIRMED
**Severity:** HIGH
**Confidence:** 1.00
**Scope:** `v7.lite.portfolio_replay` / V7 portfolio accounting
**Validated by:** Fresh 10-symbol OOS trace replay and unit negative control

**Description:** An initial interval replay accepted a second signal for the
same symbol while its prior trace position was open. The V7 default per-symbol
limit permits 5% + 5% = 10%, but this trace format represents one candidate
stream rather than scale-in instructions. The active-position map overwrote the
earlier record and lost its realization, so the preliminary `1774 selected /
161 realized` output is invalid and discarded.

**Resolution:** Replay now suppresses same-symbol signals until the prior trace
position exits. The corrected fresh replay produced `339 selected / 339
realized`, 2,236 suppressions, maximum 9 active positions, and an observational
selected-trade sum of `+1.799969R` (`+0.005310R` per selected trade). Realized R
was excluded from selection and recognized only at exit.

**Evidence:**
- `v7/lite/portfolio_replay.py`
- `v7/tests/test_lite_portfolio_replay.py`
- `reports/accp/v7_lite_checkpoint_012_fresh_interval_replay_2026-07-13.accp.yaml`

**Constraint:** This validates portfolio-replay accounting only. The fresh
window had already been inspected in research, so it is not independent alpha
promotion evidence; the volume candidate remains G0–G6 HOLD.

---

## F-019 — Current AlphaForge `net_r` Is Not a Guaranteed Simulation R-Multiple

**Status:** CONFIRMED
**Severity:** CRITICAL
**Confidence:** 1.00
**Scope:** `alphaforge/src/alphaforge/train.py` and V7-Lite trace/replay metrics
**Validated by:** Code inspection on 2026-07-13

**Description:** The canonical current label path computes forward return
`close[t+h]/close[t] - 1`, deducts a fixed 8-bps cost, and exports that value as
`net_r`. It does not divide the exported value by a stop/initial-risk amount.
The alternative triple-barrier path calculates a risk-normalized value only for
the label comparison, but also exports the unnormalized net return. Therefore
fresh AlphaForge values such as `+0.006139R` must be treated as net forward
returns until Simulation-parity labels replace them.

**Impact:** Current AlphaForge values cannot be compared to the 1R target,
cannot select Binance leverage tiers, and cannot satisfy an economic promotion
gate. Portfolio replay remains valid as selection/accounting plumbing only,
not true leveraged equity evidence.

**Evidence:**
- `alphaforge/src/alphaforge/train.py:475-500`
- `alphaforge/src/alphaforge/train.py:535-546`
- `alphaforge/src/alphaforge/train.py:417-442`
- `reports/accp/v7_lite_checkpoint_012_fresh_interval_replay_2026-07-13.accp.yaml`

**Resolution path:** P0 in
`docs/research/v7_lite_leverage_native_master_todo.md` requires
Simulation-authority true-R labels and parity tests before leverage research.

**P0 Update (2026-07-13):** `_generate_simple_labels_numba()` and `generate_labels()`
now document the semantic mismatch explicitly in docstrings (F-019 warning block).
New Simulation-authority fields `base_net_R_long` / `base_net_R_short` are available
via `LeverageOutcome` in the parity fixture.  See F-020.

---

## F-020 — P0 Economic-R Parity Foundation Implemented

**Status:** CONFIRMED
**Severity:** INFO
**Confidence:** 1.00
**Scope:** `simulation/`, `contracts/`, `alphaforge/src/alphaforge/train.py`
**Validated by:** 58 new tests (local + remote), deterministic fixture, cost scenarios

**Description:** P0 economic-R parity foundation for Binance USDⓈ-M leverage research
is implemented.  The system now has:

1. **True R semantics:** ``base_net_R`` is Simulation-authority net R at 1x base risk,
   computed as ``(exit_price - entry_price) / (ATR * stop_multiplier) - costs``.
   Forward returns and R-multiples are now distinguished in docstrings.

2. **V2 action space (13 actions):** ``NO_TRADE`` + LONG/SHORT at 1x/2x/3x/5x/7x/10x,
   backward-compatible with v1 IDs (0-8).

3. **Isolated-margin model:** ``PositionMargin`` / ``compute_isolated_margin()``
   explicit Binance liquidation formulas (ISOLATED only for P0).

4. **Deterministic parity fixture:** One symbol (BTCUSDT), 13 actions, 8 immutable
   cost scenarios, verified invariant: ``base_net_R`` does not inflate with leverage.

5. **Explicit cost scenarios:** ``CostScenario`` frozen dataclass replaces monkey-patching
   for new code paths.

**Evidence:**
- ``simulation/engine/margin.py`` — isolated margin, v2 action space mapping
- ``simulation/engine/leverage_fixture.py`` — parity fixture + cost scenarios
- ``simulation/tests/test_leverage_parity.py`` — 58 tests, all passing locally + remote
- ``simulation/contracts/models.py`` — ``PositionMargin``, ``CostScenario``, ``LeverageOutcome``,
  ``BinanceBracketSnapshot``, ``MarginType``, ``LeverageTier``
- ``contracts/schemas/action_space.schema.json`` — v2 with 13 actions
- ``contracts/registry.json`` — ActionSpace bumped to v2.0.0
- ``alphaforge/src/alphaforge/train.py`` — F-019 docstring warning

**Remote validation:** Same 58 tests pass on vast.ai RTX 3060 (host `367b847a92d6`,
Python 3.12.3, CUDA 13.0, commit `8acd3ca`). Parity fixture produces correct
`base_net_R` invariance and liquidation prices. Cost scenarios verified.

**NO simulation result has been treated as real Binance parity.** The fixture
uses deterministic synthetic candles, not exchange data.

---

## F-021 — RETRACTION: Oracle Ceiling R Must Not Be Reported as Model G3 Performance

**Status:** CONFIRMED
**Severity:** CRITICAL
**Confidence:** 1.00
**Scope:** Previous session scorecards, conversation reports
**Discovered by:** Audit on 2026-07-14
**Validated by:** Code inspection + F-019 cross-reference

**Description:** In previous sessions, a value of +0.8439 was reported as "G3
PASS MeanR=0.8439" in scorecard tables. This is categorically wrong: 0.8439 is
the **oracle ceiling R** (the label's own best-case forward return when it
selects the correct side), NOT the model's predicted-action R-multiple.

The same label that produces oracle ceiling +0.8439 yields actual model
performance of **NetR = -0.084** (from commit `2640ead`, 8,925 sample subset,
overfit_gap=0.524, PBO=HIGH). Even this -0.084 is from a tiny subset and
cannot be trusted as representative.

**Why this happened:** The label generator computes forward returns and selects
the "winning" direction as the training label. The mean R of these selected
labels is the oracle ceiling — it reflects the data's theoretical best-case,
not what the model can achieve. Reporting it as G3 conflates label quality
with model prediction quality (F-019).

**Impact:** Any scorecard showing G3 PASS with 0.8439 is invalid. The actual
G3 state remains **UNMEASURED** on the full 56-symbol panel with proper
purge/embargo and cost-adjusted labels.

**Retraction scope:**
- The value 0.8439 must NEVER appear in any G3 scorecard column
- It may be documented as `oracle_ceiling_R = +0.8439` in research notes only
- G3 can only be scored by running `walk_forward_validate` with the full panel
  and computing the model's OWN predicted-action R-multiple
- The previous session's "G3 PASS" claim is hereby retracted

**Resolution:** Faz 3 (factor selection) and subsequent training runs will
produce the real G3 measurement. Until then, G3 status = UNMEASURED.

**Evidence:**
- Commit `2640ead`: G3 reported as FAIL with NetR=0.0072 (honest measurement)
- F-019: `net_r` is forward return, not R-multiple
- Oracle ceiling derivation: label selects winning side → mean of winning-side
  forward returns = theoretical maximum, not achievable by any model
