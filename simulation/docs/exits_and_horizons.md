# Exits & Horizons — Stop, Target, Time-Exit, Unresolved, Invalidated

## Purpose

This document defines how the simulation engine determines exit conditions for each action path. Exit semantics must be deterministic, versioned, and identical across all consumers.

## Exit Families

First-phase exit reasons:

| Exit Reason | Meaning |
|---|---|
| `STOP_HIT` | Price reached the stop level before target or time exit |
| `TARGET_HIT` | Price reached the target level before stop or time exit |
| `TIME_EXIT` | Maximum holding duration reached without stop or target hit |
| `HORIZON_END` | Future path exhausted without stop, target, or time exit |
| `UNRESOLVED` | Future window is incomplete; outcome may still resolve |
| `INVALIDATED` | Required future data is corrupted, missing, or permanently unavailable |

Do not introduce excessive specialized exit families in the first version.

## Stop Logic

### Stop Level Computation

```
For LONG:
  stop_level = entry_price - (atr * stop_multiplier)

For SHORT:
  stop_level = entry_price + (atr * stop_multiplier)
```

### Stop Hit Detection

For each bar in the future path (starting from bar 1 after entry):

```
For LONG:
  if bar.low <= stop_level:
    exit_reason = STOP_HIT
    exit_price = stop_level           # conservative: worst case
    exit_bar_index = current_bar

For SHORT:
  if bar.high >= stop_level:
    exit_reason = STOP_HIT
    exit_price = stop_level
    exit_bar_index = current_bar
```

## Target Logic

### Target Level Computation

```
For LONG:
  target_level = entry_price + (atr * target_multiplier)

For SHORT:
  target_level = entry_price - (atr * target_multiplier)
```

### Target Hit Detection

For each bar in the future path:

```
For LONG:
  if bar.high >= target_level:
    exit_reason = TARGET_HIT
    exit_price = target_level
    exit_bar_index = current_bar

For SHORT:
  if bar.low <= target_level:
    exit_reason = TARGET_HIT
    exit_price = target_level
    exit_bar_index = current_bar
```

## Stop/Target Precedence

### Stop-Before-Target

In any bar, stop is checked before target. If both are triggered in the same bar:

```
if stop_hit and target_hit_in_same_bar:
    → conservative resolution: stop takes precedence
    → exit_reason = STOP_HIT
    → same_candle_ambiguity = true
    → ambiguous_resolution = "conservative_stop_first"
```

This behavior is **conservative** and **versioned**. A future version may change the precedence rule or make it mode-specific. The current version defaults to stop-first because it is safer for backtesting and avoids over-optimistic exit assumptions.

### Target-Before-Stop Variation

If a future version introduces a "target-first" or "closer-first" rule, that must:

1. Be an explicit new version of the stop/target family
2. Carry a distinct version identifier
3. Be documented in `lineage_and_versioning.md`

## Time Exit

Time exit triggers when the holding duration reaches `max_holding_bars`:

```
if exit_bar_index is None and current_bar >= max_holding_bars:
    exit_reason = TIME_EXIT
    exit_price = bar.close                 # exit at close of last legal bar
    exit_bar_index = max_holding_bars
```

Time exit is checked **after** stop and target in each bar.

## Horizon End

If the future path ends without any exit triggering:

```
if exit_bar_index is None and bar_index == last_bar_in_future_path:
    exit_reason = HORIZON_END
    exit_price = last_bar.close
    exit_bar_index = last_bar_in_future_path
```

Horizon end may also indicate that the outcome remains unresolved (see below).

## Unresolved

An outcome is `UNRESOLVED` when:

1. The future path `completeness_status` is `PARTIAL`
2. No stop, target, or time exit has been triggered
3. The horizon has not completed (fewer than `max_holding_bars` have elapsed)
4. The data may still be completed in the future

**Default behavior:**

```
unresolved remains unresolved while approved future window may still complete
unresolved becomes invalidated after 2 × configured horizon length
immediate invalidation is allowed for corrupted / irrecoverable future data
```

`UNRESOLVED` outcomes:
- Are **not** final
- Must **not** be used as training labels
- Are marked explicitly in output (`resolution_status = UNRESOLVED`)
- May transition to `COMPLETE` or `INVALIDATED` later

## Invalidated

An outcome is `INVALIDATED` when:

1. Future path `completeness_status` is `CORRUPTED`
2. Required future candles have been missing for more than `2 × horizon length`
3. Future data is irrecoverable due to exchange outage, data gap, or corruption
4. The outcome cannot be resolved consistently or safely

**Invalidation reasons:**

```yaml
invalidity_reason:
  - DATA_CORRUPTED        # Future candles contain invalid values
  - DATA_GAP              # Missing candles in the future window
  - DATA_STALE            # Future window has been pending too long (>2× horizon)
  - EXCHANGE_UNAVAILABLE  # Data source is down
  - REPLAY_BOUNDARY       # Historical replay reached the end of available data
  - STATE_INCONSISTENT    # Canonical state changed, future path no longer valid
```

`INVALIDATED` outcomes:
- Are final
- Must **not** be used as training labels
- Carry explicit `invalidity_reason`
- Are preserved in lineage for audit

## Missing Future Data

When `future_path.completeness_status == PARTIAL`:

1. The simulation engine still evaluates what it can (stop/target checks on available bars)
2. If exit has occurred (stop or target), the outcome can be `COMPLETE`
3. If no exit has occurred and `available_bars >= max_holding_bars`, resolve with `HORIZON_END` or `TIME_EXIT`
4. If no exit and `available_bars < max_holding_bars`, outcome is `UNRESOLVED`

## Corrupted Future Data

When any bar in the future path contains invalid values (NaN, negative price, zero volume when non-zero expected, timestamp out of order):

1. Simulation halts at the point of corruption
2. `resolution_status = INVALIDATED`
3. `invalidity_reason = "DATA_CORRUPTED"`
4. No further bars are evaluated

## Timing Annotation Metadata-Only Rule

Entry timing annotations (from AlphaForge feature engine or V7 runtime context) are metadata-only in the first simulation family. They:

- May be preserved in `SimulationInput.metadata.entry_timing_annotation`
- Must **not** silently shift `entry_price`
- Must **not** change stop/target levels
- Must **not** alter exit semantics

Timing-aware alternative entry semantics require a new `simulation_family_version`. Example: a future version might support "wait 1 bar then enter" semantics, but that would be a new family with an explicit version bump.

## Ambiguity Resolution Policy

### Same-Candle Stop/Target Ambiguity

In a single bar, if both stop and target levels are breached:

```
Conservative policy (first version):
  - Stop takes precedence
  - Ambiguity is recorded (same_candle_ambiguity = true)
  - Resolution is versioned and documented
```

This is not an arbitrary choice. Conservative precedence avoids over-optimistic backtest results where every ambiguous bar would otherwise be interpreted as a target hit.

### Same-Candle Exit Detection

For each bar, check in order:

1. **Stop check**: did `bar.low` (LONG) or `bar.high` (SHORT) breach the stop level?
2. **Target check**: did `bar.high` (LONG) or `bar.low` (SHORT) breach the target level?
3. If both breached: record ambiguity, apply stop-first
4. **Time exit check**: has `max_holding_bars` been reached?
5. **Horizon end check**: is this the last bar?

## Mode-Specific Exit Configuration

| Parameter | SWING | SCALP | AGGRESSIVE_SCALP |
|---|---|---|---|
| Max holding bars | 30 | 12 | 5 |
| Stop multiplier | 2.0–2.5 | 1.5–2.0 | 1.0–1.5 |
| Target multiplier | 2.0–3.0 | 1.5–2.0 | 1.0–1.5 |
| Stop-first (same candle) | yes | yes | yes |
| Invalidation multiplier | 2.0× | 2.0× | 2.0× |

## Test Requirements

- Stop hit before target
- Target hit before stop
- Same-candle stop/target ambiguity → stop-first
- Time exit after max_holding_bars
- Horizon end when path exhausted
- Unresolved when future path incomplete
- Invalidated after 2× horizon without data
- Invalidated on corrupted data
- Timing annotation does not alter exit semantics
- Exit prices match expected conservative values

---

## Document Authority

**Canonical hub:** [ai_summary.md](ai_summary.md) — read this first for the full system synthesis and table of contents.

**Related docs for this topic:**

| [contracts.md](contracts.md) | ExitResolution schema |
| [profiles.md](profiles.md) | Mode-specific stop/target/holding parameters |
| [cost_model.md](cost_model.md) | Costs applied at exit |
| [no_trade_quality.md](no_trade_quality.md) | No-trade exit evaluation |
| [lineage_and_versioning.md](lineage_and_versioning.md) | stop_family, target_family, time_exit_family versions |
    
**Parent:** [../README.md](../README.md) — authority overview and ownership diagram.

**For implementation:** See [phases/](phases/) for v4.1.1 phase plans S0–S6.

**For validation:** See [validation.md](validation.md) for required test gates.

