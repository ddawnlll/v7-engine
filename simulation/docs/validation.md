# Validation — Test Gates, Import Boundaries & Parity Requirements

## Purpose

This document defines the minimum test and validation requirements for the `/simulation` authority. Every simulation component must pass these gates before being considered production-ready.

## Test Layers

| Layer | Scope | Purpose |
|---|---|---|
| Unit tests | Individual functions/paths | Correctness of stop, target, exit, metrics, cost |
| Golden tests | Fixed input/output pairs | Catch semantic drift |
| Integration tests | Full SimulationInput → SimulationOutput flow | End-to-end correctness |
| Import boundary tests | Package imports | Enforce dependency rules |
| Parity tests | Cross-adapter comparison | Confirm paper/replay/training parity |
| Monte Carlo tests | Distributional validation | MC outputs distinguishable from realized truth |
| No-trade quality tests | No-trade classification | Saved loss, missed opportunity correctness |

## Unit Tests

### Engine Tests
- [ ] Stop hit before target (LONG)
- [ ] Stop hit before target (SHORT)
- [ ] Target hit before stop (LONG)
- [ ] Target hit before stop (SHORT)
- [ ] Same-candle stop/target ambiguity → stop-first (conservative)
- [ ] Time exit after max_holding_bars
- [ ] Horizon end when path exhausted
- [ ] Stop is checked before target in each bar
- [ ] Time exit is checked after stop and target

### Cost Tests
- [ ] Fee cost reduces net R correctly
- [ ] Slippage cost reduces net R correctly
- [ ] Gross R + total_costs = net R (within float epsilon)
- [ ] Fee computation matches expected formula
- [ ] Slippage computation matches expected formula
- [ ] Volatility-adjusted slippage > base slippage when ATR > 0
- [ ] Cost model version is included in output lineage

### Path Metrics Tests
- [ ] MFE computed correctly (highest unrealized gain)
- [ ] MAE computed correctly (deepest unrealized loss)
- [ ] MFE ≤ max(bar.high) - entry_price (LONG)
- [ ] MAE ≥ entry_price - min(bar.low) (LONG)
- [ ] time_to_mfe ≤ max_holding_bars
- [ ] time_to_mae ≤ max_holding_bars
- [ ] path_quality_score in [0, 1]
- [ ] Path metrics are deterministic for identical input

### No-Trade Tests
- [ ] Correct no-trade when both directions lose
- [ ] Saved loss when one direction loses and best wins
- [ ] Missed opportunity when best direction beats min_action_edge
- [ ] Ambiguous no-trade when action gap < ambiguity margin
- [ ] Saved loss score = 0 when both directions profitable

### Comparative Action Tests
- [ ] best_action = action with highest utility
- [ ] action_gap_r = utility(best) - utility(second_best)
- [ ] is_ambiguous = true when action_gap_r < ambiguity_margin
- [ ] NO_TRADE can be best_action when both directions lose
- [ ] Ambiguity margin is respected per mode

### Resolution Status Tests
- [ ] COMPLETE when path is complete and exit triggered
- [ ] UNRESOLVED when path is PARTIAL and no exit
- [ ] INVALIDATED when path is CORRUPTED
- [ ] INVALIDATED when missing for > 2× horizon
- [ ] invalidity_reason populated when INVALIDATED
- [ ] UNRESOLVED outcomes not marked as final

### Profile Tests
- [ ] SWING profile resolves correctly
- [ ] SCALP profile resolves correctly
- [ ] AGGRESSIVE_SCALP profile resolves correctly
- [ ] Invalid mode produces explicit error
- [ ] Profile version change produces new version in lineage

## Golden Tests

Golden tests use pre-computed input/output pairs to catch semantic drift:

```python
def test_golden_swing_long_stop_hit():
    """Swing-SWING: LONG entry, stop hit on bar 8, short target not reached."""
    input = load_golden("swing_long_stop_hit_input.json")
    expected = load_golden("swing_long_stop_hit_output.json")
    output = simulate(input)
    assert output == expected  # exact match, no tolerance for golden tests
```

Golden test fixtures are stored as read-only files. Any change to `simulation_family_version` requires updating or adding golden fixtures. Golden fixtures from previous versions must still pass with their original version's engine (regression protection).

Required golden tests:
- [ ] SWING LONG with target hit
- [ ] SWING SHORT with stop hit
- [ ] SCALP LONG with time exit
- [ ] SCALP SHORT with target hit
- [ ] AGGRESSIVE_SCALP LONG with stop hit
- [ ] AGGRESSIVE_SCALP SHORT with target hit
- [ ] Same-candle ambiguity (stop+target both triggered)
- [ ] NO_TRADE saved loss
- [ ] NO_TRADE missed opportunity
- [ ] UNRESOLVED with partial path
- [ ] INVALIDATED with corrupted data
- [ ] Fee + slippage applied correctly
- [ ] MFE/MAE correctness (complex path)

## Integration Tests

- [ ] Full SimulationInput → SimulationOutput pipeline
- [ ] All three actions produce outputs
- [ ] Lineage populated completely
- [ ] Long/short/no-trade use identical cost semantics
- [ ] Profile switching produces correct mode-specific outputs
- [ ] Multiple symbols produce correct symbol-specific outputs
- [ ] Edge case: zero-volume bar
- [ ] Edge case: single-bar future path
- [ ] Edge case: empty future path

## Import Boundary Tests

These are hard stops — failing them blocks any deployment:

- [ ] `simulation/` does not import `v7/**` (policy, risk, runtime internals)
- [ ] `simulation/` does not import `alphaforge/**` (labels, models, datasets)
- [ ] `lib/` does not import `simulation/**` (or v7 or alphaforge)
- [ ] `alphaforge/` does not contain hidden simulation truth implementation

Import boundary enforcement pattern:
```python
def test_simulation_does_not_import_v7():
    """Hard stop: /simulation must not import v7/ policy/risk/runtime."""
    violations = check_imports("simulation/", forbidden=["v7/"])
    assert len(violations) == 0, f"Import boundary violation: {violations}"
```

## Parity Tests

Verify that all adapters produce identical output for identical input:

- [ ] TRAINING adapter output == EVALUATION adapter output (same input)
- [ ] EVALUATION adapter output == REPLAY driver output (same input)
- [ ] REPLAY driver output == PAPER driver output (same input)
- [ ] Training adapter has no live execution side effects
- [ ] Evaluation adapter has no live execution side effects
- [ ] Paper driver has no live order execution (only simulation)

## Monte Carlo Tests

- [ ] Monte Carlo output carries `monte_carlo_run_id`
- [ ] Monte Carlo lineage is separate from realized truth lineage
- [ ] N paths produce N outputs
- [ ] Perturbation sigma=0 produces identical output to base (deterministic)
- [ ] target_before_stop_prob + stop_before_target_prob <= 1.0
- [ ] All path outputs are valid SimulationOutput
- [ ] Monte Carlo output never used as label source

## Hidden Simulator Audit

Search-based tests that must pass:

- [ ] No `label-only simulator` pattern anywhere in the codebase
- [ ] No `backtest-only simulator` pattern anywhere in the codebase
- [ ] No `simulation truth` owned inside v7/ outside of host/integration docs
- [ ] No `simulation_engine` implementation in alphaforge/
- [ ] No `TradeOutcome` constructed with alternative simulation logic
- [ ] No `realized_r` computed outside of /simulation or its adapters

## Timing Annotation Tests

- [ ] Entry timing annotation does not alter entry_price
- [ ] Entry timing annotation does not change stop/target levels
- [ ] Entry timing annotation does not alter exit semantics
- [ ] Timing annotation is preserved as metadata only

## Regime Visibility Tests

- [ ] Simulation output includes raw economic outcomes for all three actions
- [ ] Regime constraints recorded separately, not inside simulation output
- [ ] Regime gate metadata (`regime_gate_forced_no_trade`, `regime_blocked_direction`) visible in downstream records
- [ ] Simulation truth is never silently hidden by regime rules

## Config Tests

- [ ] All profile parameters resolve from config
- [ ] Missing config produces explicit error (not silent default)
- [ ] Invalid config value produces explicit error
- [ ] Config version mismatch detected

## Validation Commands

```bash
# Run all simulation tests
pytest simulation/tests/ -v

# Run import boundary checks only
pytest simulation/tests/import_boundary/ -v

# Run golden tests
pytest simulation/tests/golden/ -v

# Run parity tests across adapters
pytest simulation/tests/integration/test_parity.py -v

# Run hidden simulator audit
python simulation/tests/audit_hidden_simulator.py
```

## Validation Gates Before Production

Before `/simulation` is promoted to production use:

1. [ ] All unit tests pass
2. [ ] All golden tests pass
3. [ ] All integration tests pass
4. [ ] All import boundary tests pass (HARD STOP)
5. [ ] All parity tests pass
6. [ ] Hidden simulator audit passes
7. [ ] Monte Carlo tests pass
8. [ ] V7 runtime integration tests pass (hosting contract)
9. [ ] AlphaForge adapter tests pass (side-effect-free consumption)
10. [ ] No unresolved branches in phase S5 golden test coverage

---

## Document Authority

**Canonical hub:** [ai_summary.md](ai_summary.md) — read this first for the full system synthesis and table of contents.

**Related docs for this topic:**

| [architecture.md](architecture.md) | What components are tested |
| [contracts.md](contracts.md) | Contract validation rules |
| [replay_paper_and_runtime_hosting.md](replay_paper_and_runtime_hosting.md) | Adapter side-effect isolation tests |
| [lineage_and_versioning.md](lineage_and_versioning.md) | Version-aware test requirements |
    
**Parent:** [../README.md](../README.md) — authority overview and ownership diagram.

**For implementation:** See [phases/](phases/) for v4.1.1 phase plans S0–S6.

**For validation:** See [validation.md](validation.md) for required test gates.

