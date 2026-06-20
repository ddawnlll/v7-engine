# V7 Profitability Thesis

**Status:** Design Lock  
**Version:** 1.0  
**Purpose:** Single cohesive synthesis of how V7 expects to achieve positive expectancy — and under what conditions it must reject apparent edge.

---

## Purpose

This document answers:

> What is the combined edge thesis of V7, how do the pieces (mode separation, regime awareness, cost honesty, calibration, no-trade discipline, correlation control) combine into a coherent profitability argument, and what must be true for any alpha to survive V7 acceptance?

It is a **synthesis** document, not a replacement for the authority docs it references.

---

## Non-Goals

- This is not a replacement for `v7_mode_centric_architecture.md`, `pipeline/policy.md`, `pipeline/evaluation.md`, or `simulation/docs/cost_model.md`.
- This is not a live trading plan.
- This is not a performance guarantee.

---

## Canonical Profitability Chain

```
AlphaForge discovers candidate edge.
    ↓
Simulation measures cost-honest economic truth.
    ↓
V7 converts validated edge into accept/reject policy decisions.
    ↓
Runtime operates lifecycle and execution eligibility.
    ↓
Interface observes only.
```

**V7 does not invent alpha.** AlphaForge discovers candidate alpha.  
**AlphaForge does not own final trade decisions.** V7 owns policy acceptance.  
**Simulation owns economic truth.** No component may bypass simulation costs.  
**Runtime does not override policy with model confidence.**  

---

## System-Level Profitability Thesis

> V7 can only be profitable if mode-specific AlphaForge discoveries survive Simulation's cost-honest truth layer and then pass V7's no-trade-first, regime-aware, calibrated expected-R, risk, portfolio, and promotion gates.

The thesis does not rely on any single mechanism. Edge emerges from the combination of:

1. **Mode-specific timeframes** capturing different market structures (SWING: trend, SCALP: mean-reversion, AGGRESSIVE_SCALP: micro-structure) — each timeframe regime reveals different inefficiencies.
2. **Cost-honest labels** via unified simulation — training and evaluation both see the same fee, slippage, and net-R truth.
3. **Regime-aware policy** — counter-trend trades blocked in TREND_UP/TREND_DOWN; NO_TRADE defaulted in TRANSITION.
4. **NO_TRADE as first-class action** — economically valid; measured via CORRECT_NO_TRADE, SAVED_LOSS, MISSED_OPPORTUNITY, AMBIGUOUS_NO_TRADE.
5. **Hybrid model outputs** (classification + regression) enabling dual gates: action probability AND economic quality.
6. **Calibrated decision surfaces** — probability and expected-R surfaces must be trustworthy enough for policy thresholds.
7. **Correlation-aware portfolio control** — prevents overexposure to single clusters.
8. **Independent per-mode promotion** — each mode earns its own live eligibility; no cross-mode contamination.

---

## AlphaForge Discovery Thesis

AlphaForge is the **discovery authority**. It researches anomaly patterns, proposes alpha hypotheses, runs statistical validation, and produces candidate reports. Three hypotheses are currently under investigation (see `alpha_thesis_validation_plan.md`):

| Alpha ID | Description | Status |
|----------|-------------|--------|
| ALTCOIN_DELAY | BTC movement followed by delayed altcoin reaction | Research candidate |
| VOLATILITY_COMPRESSION | Low volatility compression → breakout/expansion | Research candidate |
| FUNDING_DIVERGENCE | Funding/spot/perp divergence → directional pressure | Research candidate (data-dependent) |

**Critical rule:** Alpha hypotheses are research candidates, not locked profitable truths. Each must pass independent validation before being attached to any mode's promotion gate.

---

## Simulation Economic Truth Requirements

Simulation owns economic truth. For V7 to trust an alpha:

- Fee cost (taker: 4bp, maker: 2bp) must be applied to every simulated path.
- Slippage cost (base 1bp, volatility-adjusted) must be applied to entry and exit.
- Funding cost must be applied for perpetual swaps (see `simulation/docs/cost_model.md` funding section).
- Stop-before-target in same candle (conservative, versioned).
- Exit families must be mode-specific (see `simulation/docs/exits_and_horizons.md`).

**Without cost-honest simulation, V7 cannot distinguish real edge from statistical artifact.** Backtest pass without cost-honest labels is not evidence of profitability.

---

## V7 Policy Conversion Thesis

V7 policy converts simulation-validated edge into accept/reject decisions through these gates (see `pipeline/policy.md`):

1. Probability/confidence gate
2. No-trade comparison gate
3. Decision margin gate
4. Expected-R gate
5. Cost-adjusted expectancy gate
6. Adverse-pressure/drawdown gate
7. Regime consistency gate
8. Degradation/fallback gate

Regime modifiers (from `v7_regime_aware_extensions.md`):
- TREND_UP: blocks SHORT
- TREND_DOWN: blocks LONG
- RANGE: raises thresholds
- TRANSITION: strongly prefers NO_TRADE

---

## Mode-Specific Edge Thesis

| Mode | Edge Source | Cost Sensitivity | No-Trade Discipline | Key Risk |
|------|------------|------------------|---------------------|----------|
| SWING (4h) | Trend-following over multi-day horizons; regime alignment amplifies edge | MEDIUM — wide stops dilute per-trade cost impact but holding periods accumulate funding | LOW tendency — trades unless ambiguous | Overnight/weekend gap; funding accumulation over 30-bar holds |
| SCALP (1h) | Mean-reversion and micro-trends; cost-adjusted expectancy gate REQUIRED | HIGH — costs are proportionally larger on smaller R targets | MEDIUM tendency — NO_TRADE when ambiguous | Slippage on entry/exit dominates edge; stale signals decay fast |
| AGGRESSIVE_SCALP (15m) | Micro-structure inefficiencies; strong signal required to overcome HIGH no-trade default | VERY HIGH — costs can erase entire edge; instant_adverse_threshold at -0.05R | HIGH tendency (default) — trades only on strong confluence | Cost/slippage can make mode net-negative even with good signals; order book required for Phase 3 |

### Minimum Success Thresholds (from `pipeline/labels.md`)

| Mode | Min Net R | Max MAE | Cost-Adj Expectancy | Max Time to MFE |
|------|-----------|---------|---------------------|-----------------|
| SWING | 0.75R | -0.60R | not required | not required |
| SCALP | 0.20R | -0.25R | ≥ 0.10R | not required |
| AGGRESSIVE_SCALP | 0.10R | -0.10R | not required | ≤ 3 bars |

### Mode Priority Model

| Mode | Business Priority | Research Priority | Threshold Status | AlphaForge Report | Promotion Readiness |
|------|------------------|-------------------|-----------------|-------------------|---------------------|
| SCALP | **PRIMARY** | **PRIMARY** | HOLD (empirical evidence required) | Primary research report | Not ready until evidence |
| AGGRESSIVE_SCALP | **PRIMARY** | **PRIMARY** | HOLD (empirical evidence required) | Primary research report | Not ready until evidence |
| SWING | SECONDARY_BASELINE | SECONDARY_BASELINE | LOCKED_INITIAL_BASELINE | Secondary baseline report | Baseline ready; recalibration required after first evidence |

**SCALP and AGGRESSIVE_SCALP are PRIMARY business/research modes.** V7's main profitability thesis is driven by shorter-term edge discovery, anomaly capture, and cost-aware fast reaction. SWING serves as a control/baseline anchor — it validates the architecture with lower risk but is not the primary product target.

**HOLD on SCALP/AGGRESSIVE_SCALP means empirical research required, not low priority.** Fee, slippage, latency, and overfit risks make these modes harder to lock without evidence. Their HOLD status reflects research difficulty, not business importance.

---

## Alpha Hypothesis Mapping

Each alpha hypothesis maps to likely compatible modes. This mapping is **directional**, not prescriptive — each alpha must be validated independently per mode.

| Alpha ID | Likely Modes | Not Recommended Modes | Required Features | Required Simulation Outputs | Required Cost Assumptions | Validation Gate | Rejection Conditions | Owner |
|----------|-------------|----------------------|-------------------|----------------------------|--------------------------|-----------------|---------------------|-------|
| ALTCOIN_DELAY | SWING, SCALP | AGGRESSIVE_SCALP | BTC/altcoin return correlation, cross-sectional momentum, volume ratio | long_R_net, short_R_net, best_action_label, no_trade_quality | Fee + slippage; funding deferred for perps | Walk-forward 12-fold, R > 1.5, beats all 3 baselines | Only works in 1 regime; loses to random baseline; R < 1.0 | AlphaForge |
| VOLATILITY_COMPRESSION | SCALP, AGGRESSIVE_SCALP | SWING | ATR percentile, volatility ratio, breakout detection, volume expansion | long_R_net, short_R_net, time_to_mfe_bars, exit_efficiency | Fee + slippage; funding not applicable (spot) | Breakout success > 40%; beats random direction | False breakout dominates; direction randomness untestable | AlphaForge |
| FUNDING_DIVERGENCE | SWING, SCALP | AGGRESSIVE_SCALP | Funding rate, spot/futures return divergence, open interest delta | long_R_net, short_R_net, funding_cost_r, cost_adjusted_expectancy | **Funding cost model REQUIRED** — cannot promote without it | Directional accuracy > 45%; data availability verified first | Data unavailable; directional accuracy < 45%; only works on BTC | AlphaForge |

**Mandatory principle:** Each alpha must be validated per mode independently. AlphaForge proposes edge; V7 promotion gate decides acceptance. Funding Divergence cannot be promoted for perpetuals until the funding cost model is documented.

---

## Cost-Honesty Requirements

- One cost model for all consumers (labels, evaluation, paper, live).
- Fee: taker 4bp both sides (conservative default).
- Slippage: 1bp base, volatility-adjusted.
- Funding: explicitly LOCKED, DEFERRED, or LOCK_CANDIDATE (see `simulation/docs/cost_model.md`).
- All costs expressed in R terms: `realized_r_net = realized_r_gross - fee_cost_r - slippage_cost_r - funding_cost_r`.

**Any alpha that cannot survive costs must be rejected regardless of apparent model accuracy.**

---

## No-Trade Discipline

NO_TRADE is an economically valid action. The system must measure:

- **CORRECT_NO_TRADE:** Best directional action would have lost or been marginal.
- **SAVED_LOSS:** NO_TRADE avoided a real loss.
- **MISSED_OPPORTUNITY:** NO_TRADE missed a real gain.
- **AMBIGUOUS_NO_TRADE:** Unclear whether skip was good or bad.

Per-mode no-trade quality thresholds (from `simulation/docs/no_trade_quality.md`):

| Mode | Saved-Loss Threshold | Missed-Opportunity Threshold | No-Trade Correctness Threshold |
|------|---------------------|------------------------------|-------------------------------|
| SWING | 0.20R | 0.35R | 0.20R |
| SCALP | 0.10R | 0.15R | 0.10R |
| AGGRESSIVE_SCALP | 0.05R | 0.08R | 0.05R |

A model that avoids all trades looks safe but is not automatically good — missed-opportunity quality must be measured.

---

## Calibration and Expected-R Discipline

- Per-mode calibration (global within scope, not per-symbol) — see `pipeline/calibration.md`.
- Classification calibration: p_long_now, p_short_now, p_no_trade must reflect realized frequencies.
- Regression reliability: predicted-R buckets must match realized-R averages.
- Calibration drift monitoring is required (see `pipeline/monitoring.md`).

**If calibration is not trustworthy enough for policy thresholds, the mode must be rejected or downgraded to research-only.**

---

## Portfolio and Correlation Discipline

- Pre-computed correlation groups: btc_cluster, eth_cluster, layer1, defi (see `pipeline/portfolio.md`).
- Max cluster exposure: 15%.
- Directional exposure limits enforced at portfolio stage before risk.
- Cluster suppression applied before risk gate.

---

## Promotion and Rejection Philosophy

Promotion is **earned per mode**, not inherited from architecture sophistication.

Gate sequence (see `pipeline/evaluation.md` for full details):
G0_DOC_READY → G1_RESEARCH_BACKTEST → G2_WALK_FORWARD_OOS → G3_COST_STRESS → G4_REGIME_BREAKDOWN → G5_SYMBOL_STABILITY → G6_CALIBRATION_RELIABILITY → G7_SHADOW → G8_PAPER → G9_TINY_LIVE → G10_LIVE

### Mandatory Rejection Rules

1. Reject if profitability only appears before costs.
2. Reject if edge disappears under slippage stress.
3. Reject if one symbol or cluster dominates results.
4. Reject if regime breakdown shows unacceptable hidden fragility.
5. Reject if NO_TRADE quality is poor.
6. Reject if calibration is not trustworthy enough for policy thresholds.
7. Reject if paper/shadow diverges materially from backtest expectations.
8. Reject if alpha cannot survive cost, slippage, funding, no-trade comparison, regime breakdown, symbol stability, and walk-forward OOS validation — **regardless of apparent model accuracy.**

---

## Failure Modes

| Failure Mode | Detection | Mitigation |
|-------------|-----------|------------|
| Backtest overfitting | Walk-forward OOS divergence | Reject; re-examine feature set and label design |
| Cost model drift | Monitoring cost_model_version vs realized costs | Bump version; re-label; re-evaluate |
| Regime detection rot | Regime stability metrics degrade | Re-tune or replace detector |
| Calibration decay | Reliability error rising | Re-calibrate; if persistent, reject mode |
| Single-symbol edge | Symbol breakdown shows one symbol dominates | Reject until edge diversifies |
| Promotion without paper evidence | Direct backtest→live attempt | Blocked by G7/G8/G9 gates |
| Mode confusion | Runtime routes to wrong mode artifact | Scope compatibility validation |

---

## Locked Decisions

- Three mode-centric pipelines (SWING, SCALP, AGGRESSIVE_SCALP) — see `DEC-001`.
- LONG_NOW / SHORT_NOW / NO_TRADE action space — see `DEC-002`.
- NO_TRADE as first-class action — see `DEC-003`.
- XGBoost-first hybrid model per mode — see `DEC-004`.
- Features shared, labels mode-specific — see `DEC-005`.
- One simulation truth layer — see `DEC-006`.
- Rule-based regime detection (Phase 1) — see `DEC-007`.
- Regime is policy-layer, not simulation-layer — see `DEC-008`.
- One cost model for all consumers — see `DEC-009`.
- Walk-forward evaluation — see `DEC-010`.
- Promotion requires OOS economic evidence — see `DEC-011`.
- Runtime is not the model — see `DEC-012`.
- Regime-aware policy modifiers — see `DEC-013`.
- Correlation-aware portfolio — see `DEC-014`.
- Stop-before-target in same candle — see `DEC-015`.
- SWING is secondary baseline / control mode with LOCKED_INITIAL_BASELINE thresholds — see `DEC-016`. SCALP and AGGRESSIVE_SCALP are PRIMARY business/research modes.
- **DEC-024:** SCALP is a PRIMARY business/research mode — V7's main edge search targets shorter-term opportunities, anomaly capture, and cost-aware fast reaction.
- **DEC-025:** AGGRESSIVE_SCALP is a PRIMARY business/research mode — high risk but potentially high edge density; requires empirical evidence before promotion.
- **DEC-026:** SWING is SECONDARY_BASELINE / CONTROL mode — locked first because it is safer and easier to baseline, not because it is the primary product.
- **DEC-027:** HOLD on SCALP/AGGRESSIVE_SCALP means "empirical research required" — not "low priority."
- **DEC-028:** AlphaForge must produce primary research reports for SCALP and AGGRESSIVE_SCALP, and a secondary baseline/control report for SWING.
- **DEC-029:** Promotion-readiness and research-priority are independent dimensions. SWING is more promotion-ready; SCALP/AGGRESSIVE_SCALP have higher business/research priority.
- SWING promotion thresholds are LOCKED_INITIAL_BASELINE (owner-reviewed, recalibratable baselines) — see `DEC-017`.
- SCALP promotion thresholds remain HOLD until empirical evidence exists — see `DEC-018`.
- AGGRESSIVE_SCALP promotion thresholds remain HOLD until empirical evidence exists — see `DEC-019`.

---

## Open Decisions

| Area | Current State | Owner Review |
|------|--------------|--------------|
| Funding cost model for perpetuals | DEFERRED — see `simulation/docs/cost_model.md` | Simulation authority |
| **SWING promotion thresholds** | **LOCKED_INITIAL_BASELINE** — owner-reviewed conservative baselines in `pipeline/evaluation.md`; recalibration required after first walk-forward | ✅ **P0.7C complete** |
| **SCALP promotion thresholds** | **HOLD** — empirical evidence required before any numeric lock; placeholder values in `pipeline/evaluation.md` are not implementation-ready | V7 authority (post-first-evidence) |
| **AGGRESSIVE_SCALP promotion thresholds** | **HOLD** — empirical evidence required before any numeric lock; placeholder values in `pipeline/evaluation.md` are not implementation-ready | V7 authority (post-first-evidence) |
| Mode-specific risk parameters (exact numeric values) | LOCK_CANDIDATE defaults in `pipeline/risk.md` | V7 authority |
| Minimum training sample per mode | LOCK_CANDIDATE in `pipeline/dataset.md` | V7 authority |
| Per-mode independent runtime lifecycle | Documented in `runtime/runtime_integration.md` | V7 authority |

---

## P0.7C Threshold Lock Decisions

| Decision ID | Decision | Status |
|-------------|----------|--------|
| DEC-017 | SWING is the only mode with LOCKED_INITIAL_BASELINE promotion thresholds. All 10 thresholds (min OOS window, min trades, min expectancy R, max drawdown, min no-trade quality, calibration, cost stress, shadow duration, paper duration, tiny live limit) are owner-reviewed conservative baselines. Recalibration required after first SWING walk-forward. | **LOCKED (P0.7C)** |
| DEC-018 | SCALP remains HOLD for numeric promotion thresholds. Placeholder values in evaluation.md are not live, not locked, not implementation-ready. No promotion threshold logic for SCALP may be implemented without empirical evidence and owner review. | **HOLD (P0.7C)** |
| DEC-019 | AGGRESSIVE_SCALP remains HOLD for numeric promotion thresholds. Same constraints as SCALP. | **HOLD (P0.7C)** |
| DEC-020 | All SWING LOCKED_INITIAL_BASELINE thresholds require explicit recalibration after first SWING walk-forward evidence. Recalibration is owner-reviewed, not automated. | **LOCKED (P0.7C)** |
| DEC-021 | Funding cost model remains DEFERRED. Perpetual swap live promotion (G3+) blocked until funding model is locked. This hold does not block spot-only SWING implementation. | **HOLD (carry-forward)** |

---

## References

- `vision.md` — Primary goal, success definition, promotion rule
- `architecture.md` — Mode-centric architecture, truth hierarchy
- `v7_mode_centric_architecture.md` — Complete mode specification
- `v7_regime_aware_extensions.md` — Regime detection, policy modifiers
- `pipeline/labels.md` — Mode-specific label semantics
- `pipeline/model.md` — XGBoost-first hybrid model
- `pipeline/policy.md` — Decision gates, regime modifiers
- `pipeline/evaluation.md` — Promotion gates, walk-forward
- `pipeline/risk.md` — Risk controls, kill switches
- `pipeline/portfolio.md` — Correlation-aware portfolio
- `pipeline/calibration.md` — Per-mode calibration
- `pipeline/monitoring.md` — Drift detection
- `simulation/docs/cost_model.md` — Fee, slippage, net R
- `simulation/docs/profiles.md` — Mode-specific simulation profiles
- `simulation/docs/exits_and_horizons.md` — Exit families
- `simulation/docs/no_trade_quality.md` — No-trade quality classification
- `alpha_thesis_validation_plan.md` — Alpha hypotheses under investigation
- `roadmap.md` — Implementation sequencing
