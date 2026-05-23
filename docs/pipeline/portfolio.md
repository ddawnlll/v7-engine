# Pipeline Portfolio — Correlation-Aware

**Intended path:** `docs/v7/pipeline/portfolio.md`

## Purpose

Defines how V7 handles cross-symbol portfolio interaction after single-candidate policy output exists — **with correlation-aware exposure controls**.

It answers:

> Given multiple candidate decisions across symbols, how should V7 reason about exposure, concentration, cross-symbol competition, and effective correlation risk?

---

## Core Decision

V7 is designed for a centralized multi-symbol world.

Portfolio logic is first-class but lightweight in first phase. It is not the model and not a full optimizer. **Correlation-aware controls prevent cluster overexposure** (section 6.7 of the mode-centric architecture).

---

## First-Phase Scope

- target universe up to 60 symbols
- initial rollout may use a smaller subset
- portfolio layer may pass, suppress, down-rank, or annotate
- **correlation groups are pre-computed and versioned**
- portfolio layer should not become a full optimizer in first phase

---

## Inputs

- policy-approved candidate results
- action probabilities
- expected R by action
- confidence
- current portfolio context
- exposure state
- **symbol cluster/correlation metadata (pre-computed)**
- **correlation group definitions**
- portfolio config

---

## Outputs

Portfolio stage produces:

- pass / suppress / down-rank / annotate
- portfolio interpretation
- suppression reason if blocked
- ranking metadata where relevant
- portfolio pressure score where configured
- **cluster exposure breakdown**
- **effective exposure warnings**

---

## Ranking Rule

When multiple candidates compete, first-phase ranking should use:

1. policy-approved actionability
2. expected-R quality
3. cost-adjusted expectancy
4. confidence as secondary ordering
5. portfolio pressure adjustments
6. deterministic tie-break by symbol order only as last resort

Use suppression instead of down-ranking when:

- a hard portfolio cap is exceeded
- cluster concentration would breach configured limits
- portfolio context is degraded and config requires safe non-execution

---

## Rules

1. Portfolio is not the model.
2. Portfolio suppression must be visible.
3. Portfolio should not hide risk vetoes.
4. Lightweight first phase.
5. Regression expected-R can inform ranking, but cannot override hard caps.
6. **Effective exposure accounts for correlation, not just position count.**

---

## Correlation-Aware Exposure Control

Portfolio uses **pre-computed correlation groups** to prevent effective overexposure:

```python
CORRELATION_GROUPS = {
    "btc_cluster": {"BTCUSDT", "WBTCUSDT", "BTCB.*"},
    "eth_cluster": {"ETHUSDT", "ETH.*"},
    "layer1": {"SOLUSDT", "ADAUSDT", "DOTUSDT", "AVAXUSDT"},
    "defi": {"UNIUSDT", "AAVEUSDT", "MKRUSDT"},
}
```

### Effective Exposure Calculation

- Total effective exposure = sum of position sizes **within each correlation group**
- If a group's effective exposure exceeds `max_cluster_exposure` (default 15%), suppress additional candidates from that group
- Directional exposure limits also apply per group

### Cluster Suppression Rule

```python
def should_allow_new_position(new_pos, current_positions):
    # 1. Check cluster exposure
    new_group = get_correlation_group(new_pos["symbol"])
    current_cluster_exp = current_exposure["clusters"].get(new_group, 0.0)
    if current_cluster_exp + new_pos["size_pct"] > max_cluster_exposure:
        return False, f"cluster_{new_group}_limit"
    # 2. Check direction limits
    if new_pos["side"] == "LONG":
        if total_long + new_pos["size_pct"] > max_direction_exposure:
            return False, "long_direction_limit"
    # 3. Similar for SHORT
    return True, "allowed"
```

---

## Cluster Definition

First-phase cluster families use:

- approved manual groupings (versioned)
- stable correlation-based groups computed offline and versioned

Do not compute ad hoc runtime clusters without a versioned grouping family.

---

## Portfolio Context Unavailable Rule

If portfolio context is unavailable:

- degrade explicitly
- default first-phase behavior is safe non-execution unless config explicitly allows lighter fallback

Do not silently assume zero portfolio pressure.

---

## DecisionEvent Mapping

Set `DecisionEvent.runtime_interpretation.portfolio_blocked = true` when the portfolio stage returns:

- `SUPPRESSED`
- `BLOCKED`

Down-ranked but still admissible candidates should not set `portfolio_blocked = true`.

---

## Recommended Controls

- max simultaneous positions
- cluster exposure caps (per correlation group)
- symbol concentration caps
- drawdown-state pressure modifiers
- optional per-session ranking limits
- duplicate candidate suppression before risk gate where configured

---

## Config Surface

Key config families:

- max open positions
- exposure caps
- cluster grouping rules
- correlation group definitions
- portfolio suppression thresholds
- ranking family
- portfolio context fallback behavior

---

## Interfaces

Upstream:

- `pipeline/policy.md`

Downstream:

- `pipeline/risk.md`
- `contracts/decision_event.md`
- `contracts/trade_outcome.md`

---

## Test Requirements

Minimum tests:

- concentration suppression works
- **correlation-aware cluster suppression works**
- cluster suppression is visible
- rank vs suppress is deterministic
- expected-R influences ranking only within allowed caps
- `portfolio_blocked` mapping is correct
- unavailable context degrades visibly

---

## Final Position

Portfolio logic keeps individually good trades from becoming collectively bad exposure. It uses expected economic quality and **correlation-aware cluster controls**, but it must remain explicit and lightweight in first phase.
