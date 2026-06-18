# Pipeline Risk

**Intended path:** `docs/v7/pipeline/risk.md`

## Purpose

Defines hard and soft risk controls applied after policy and portfolio stages.

It answers:

> Given a candidate decision, what risk rules may block, degrade, or allow execution eligibility?

---

## Core Decision

Risk is separate from model, calibration, policy, and portfolio.

A trade can be economically attractive and still operationally unsafe.

---

## Inputs

- candidate decision
- policy interpretation
- portfolio interpretation
- account/exposure state
- result freshness
- degradation flags
- risk config

---

## Outputs

Risk stage produces:

- pass / block / degrade
- risk interpretation
- explicit block reason
- cooldown reason where relevant
- exposure reason where relevant
- stale/degraded-result reason where relevant

---

## Stage Order

First-phase order:

1. policy
2. portfolio
3. risk
4. runtime execution eligibility

If both portfolio and risk block, preserve both signals when available. Treat risk as the final hard gate when the block is risk-hard.

---

## Rules

1. No hidden risk veto.
2. Hard guards stay hard.
3. Model confidence and expected R cannot override operational limits.
4. Keep risk readable.
5. Separate economic actionability from execution eligibility.

---

## Recommended First-Phase Controls

- global kill switch
- cooldown after loss / major event
- max gross exposure
- max per-symbol exposure
- max cluster exposure
- duplicate-position protection
- stale-result rejection
- degraded-result safe action rules
- minimum account/context integrity requirements

---

## Mode-Specific Risk Parameters

Each mode has distinct risk tolerances derived from its timeframe, holding period, cost sensitivity, and no-trade tendency. Values marked **LOCK_CANDIDATE** are conservative defaults requiring owner review before implementation.

### Risk Parameter Table

| Parameter | SWING | SCALP | AGGRESSIVE_SCALP | Owner Review |
|-----------|-------|-------|------------------|--------------|
| Max mode exposure (% of account) | 25% **[LOCK_CANDIDATE]** | 15% **[LOCK_CANDIDATE]** | 5% **[LOCK_CANDIDATE]** | Required |
| Max per-symbol exposure (% of account) | 10% **[LOCK_CANDIDATE]** | 5% **[LOCK_CANDIDATE]** | 2% **[LOCK_CANDIDATE]** | Required |
| Max cluster exposure (% of account) | 15% (from portfolio.md) | 15% (from portfolio.md) | 15% (from portfolio.md) | Locked |
| Max daily loss (% of account) | 5% **[LOCK_CANDIDATE]** | 3% **[LOCK_CANDIDATE]** | 2% **[LOCK_CANDIDATE]** | Required |
| Max drawdown (cumulative) | 25% **[LOCK_CANDIDATE]** | 15% **[LOCK_CANDIDATE]** | 10% **[LOCK_CANDIDATE]** | Required |
| Cooldown after loss | 4 bars (16h at 4h) **[LOCK_CANDIDATE]** | 6 bars (6h at 1h) **[LOCK_CANDIDATE]** | 12 bars (3h at 15m) **[LOCK_CANDIDATE]** | Required |
| Stale result TTL | 1 bar (4h) **[LOCK_CANDIDATE]** | 2 bars (2h) **[LOCK_CANDIDATE]** | 4 bars (1h) **[LOCK_CANDIDATE]** | Required |
| Duplicate position rule | Block same symbol + same direction | Block same symbol + same direction | Block same symbol + same direction | Locked |
| Kill switch sensitivity | MODERATE — trigger on drawdown breach or 3 consecutive losses | HIGH — trigger on drawdown breach, 2 consecutive losses, or cost divergence | VERY HIGH — trigger on drawdown breach, any single unexpected loss > 2× expected, cost divergence, or stale result cascade | Required for VERY HIGH |

### Design Policy

1. **SWING may tolerate wider stop/horizon but must have strict drawdown and cluster exposure controls.** Larger position size, longer holding period — the damage from a single bad trade is proportionally larger.
2. **SCALP must have stricter stale-result and cost sensitivity controls than SWING.** Higher trade frequency means more opportunities for stale signals and cost accumulation to erode edge.
3. **AGGRESSIVE_SCALP must have the strictest stale-result, slippage, no-trade, cooldown, and kill-switch controls.** Highest frequency, smallest edge per trade, most sensitive to execution quality degradation.
4. **Do not use Kelly sizing in Phase 1** unless explicitly locked by a separate authority decision. Phase 1 uses fixed sizing.
5. **Model confidence cannot override risk gates.** A high-confidence signal with unacceptable drawdown risk must be blocked.
6. **Promoted SWING status does not imply SCALP or AGGRESSIVE_SCALP readiness.** Each mode earns its own risk eligibility independently.

### Mode-Specific Risk Rationale

| Mode | Primary Risk Concern | Risk Mitigation |
|------|---------------------|-----------------|
| SWING | Single large adverse move over multi-day hold; gap risk over weekends | Strict per-symbol and cluster limits; cooldown after loss prevents revenge trading on higher timeframe |
| SCALP | Cost erosion over many small trades; stale signals at 1h decay | Stricter stale-result TTL; cost-adjusted expectancy gate in policy; cooldown after consecutive losses |
| AGGRESSIVE_SCALP | Slippage/cost can erase entire edge; micro-structure noise produces false signals | Most restrictive stale-result TTL; strictest kill switch; highest cooldown frequency; smallest position sizes |

### Forbidden

- Do not use Kelly sizing in Phase 1 unless already explicitly locked.
- Do not allow model confidence to override risk gates.
- Do not allow promoted SWING status to imply SCALP or AGGRESSIVE_SCALP readiness.
- Do not relax AGGRESSIVE_SCALP risk controls because SWING is profitable.

---

## Cooldown Rule

Cooldown is configurable by:

- trigger family
- duration in bars or minutes
- scope: global, symbol-local, direction-local

Default numeric values belong in config.

---

## Duplicate Protection

Detect at minimum:

- same symbol, same direction, existing open position
- same symbol, same direction, already accepted decision in the same batch/session where duplication is forbidden

---

## Degraded Result Handling

If classification surfaces are valid but regression surfaces are degraded, policy may already select no-trade. If such a result reaches risk, risk must still see the degradation flag.

If risk context is unavailable:

- degrade explicitly
- prefer safe non-execution when required by config

---

## Config Surface

Key config families:

- kill-switch settings
- cooldown rules
- exposure hard limits
- stale-result limits
- degraded-result behavior
- duplicate protection rules
- minimum context requirements

---

## Interfaces

Upstream:

- `pipeline/portfolio.md`
- `runtime/runtime_integration.md`

Downstream:

- `contracts/decision_event.md`
- `contracts/trade_outcome.md`
- runtime execution eligibility

---

## Test Requirements

Minimum tests:

- hard block visibility
- cooldown behavior
- duplicate protection
- stale result block
- degraded result handling
- actionability vs execution-eligibility separation
- portfolio-before-risk ordering preserved

---

## Final Position

Risk is the final safety layer before execution eligibility. It must stay explicit, conservative, and auditable.
