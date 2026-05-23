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
