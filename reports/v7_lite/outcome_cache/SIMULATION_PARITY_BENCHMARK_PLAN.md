# Simulation Parity Benchmark Plan (P0)

**Status:** `PLAN_COMPLETE`
**Generated:** 2026-07-08
**Economic truth authority:** `simulation/` — all simulation semantics are defined in `simulation/docs/`

---

## Objective

Prove that the CPU outcome cache produces **identical exit bar, exit reason, and net_R**
as the authoritative simulation engine (`simulation/`). Any discrepancy between
the outcome cache and the simulation engine means the cache produces wrong results.

---

## Economic Truth Authority Files

The following files define simulation truth and must be treated as authoritative:

| File | Purpose |
|------|---------|
| `simulation/docs/contracts.md` | SimulationInput, SimulationOutput, ActionOutcome, ExitResolution schemas |
| `simulation/docs/profiles.md` | Per-mode stop/target multipliers, max holding bars |
| `simulation/docs/cost_model.md` | Fee/slippage formulas, net R computation |
| `simulation/docs/exits_and_horizons.md` | Stop/target/time-exit precedence rules, same-candle ambiguity |
| `simulation/docs/ai_summary.md` | Consolidated reference |
| `simulation/src/simulation/engine.py` (if exists) | Reference implementation |
| `simulation/src/simulation/authority.py` | Cost authority constants |

---

## Six Parity Targets (P0)

### Target 1: exit_bar Agreement ≥ 99.9%

**Definition:** For every candidate trade, the exit bar (index of the candle
where the trade exits) must match between outcome cache and simulation engine.

**Test:**
```python
def test_exit_bar_agreement():
    for candidate in test_fixtures:
        sim_result = simulation_engine.run(candidate)
        cache_result = outcome_cache.lookup(candidate.alpha_id, candidate.symbol, candidate.entry_bar)
        assert cache_result.exit_bar == sim_result.exit_bar, \
            f"Mismatch at {candidate.alpha_id}/{candidate.symbol}/{candidate.entry_bar}"
```

**Fixture requirements:** 10,000 diverse candidates covering:
- All exit reasons (STOP_HIT, TARGET_HIT, TIME_EXIT, HORIZON_END, INVALIDATED)
- All 4 symbols (BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT)
- Both directions (LONG, SHORT)
- Same-candle stop/target conflicts
- Missing future data (partial windows)

**Threshold:** ≥ 99.9% agreement across all fixtures.

### Target 2: exit_reason Agreement ≥ 99.9%

**Definition:** Exit reason string must match byte-for-byte between cache and engine.

**Test:**
```python
def test_exit_reason_agreement():
    for candidate in test_fixtures:
        sim_reason = simulation_engine.run(candidate).exit_reason
        cache_reason = outcome_cache.lookup(...).exit_reason
        assert sim_reason == cache_reason
```

**Special cases to fixture:**
- Stop and target on same candle (precedence: stop wins, ambiguity flagged)
- Time exit at exact horizon end
- Partial future window → HORIZON_END or INVALIDATED

### Target 3: net_R Tolerance Pass

**Definition:** Net R values must agree within 1e-6 (floating point tolerance).

**Test:**
```python
def test_net_r_tolerance():
    for candidate in test_fixtures:
        sim_r = simulation_engine.run(candidate).net_R
        cache_r = outcome_cache.lookup(...).net_R
        assert abs(sim_r - cache_r) < 1e-6
```

### Target 4: Same-Bar Stop/Target Conflict Fixture

**Definition:** When stop and target are hit in the same candle, simulation
defines stop as the exit reason (conservative). Cache must replicate this.

**Fixture:**
- Entry at bar T, price 50000
- Stop at 49500 (-1.0R)
- Target at 51000 (+2.0R)  
- Candle T+1 has LOW=49000, HIGH=51500 (both levels breached)
- Expected: exit_reason = `STOP_HIT`, exit_price ≈ 49500

### Target 5: Fee/Slippage Parity Pass

**Definition:** Fee_R, slippage_R, and their sum must match simulation output.

**Test:**
```python
def test_fee_slippage_parity():
    config = SimulationProfile(mode="SCALP", taker_fee_bps=4.0, slippage_bps=1.0)
    for candidate in test_fixtures:
        sim = simulation_engine.run(candidate, config)
        cache = outcome_cache.lookup(candidate.alpha_id, candidate.symbol, candidate.entry_bar)
        assert abs(sim.fee_R - cache.fee_R) < 1e-6
        assert abs(sim.slippage_R - cache.slippage_R) < 1e-6
```

### Target 6: Timeout Exit Parity Pass

**Definition:** When no stop or target is hit within max_holding_bars, trade
exits at close of max_holding_bars candle with exit_reason=TIME_EXIT.

**Fixture:**
- Max holding bars = 12 (SCALP mode)
- Entry bar T, price 50000, stop at 45000, target at 55000
- Bars T+1 through T+12: price stays within 45000-55000
- Expected: exit at bar T+12, exit_reason=TIME_EXIT

---

## Test Fixture Generation

### Fixture Generation Script

```python
# alphaforge/tests/fixtures/generate_parity_fixtures.py

PARITY_FIXTURES_V1 = [
    # [symbol, direction, entry_price, stop_price, target_price, 
    #  max_bars, expected_exit_bar, expected_exit_reason, expected_net_R]
    
    # Case 1: Normal stop hit
    ("BTCUSDT", "LONG", 50000, 49000, 52000, 12, 3, "STOP_HIT", -1.0),
    
    # Case 2: Normal target hit  
    ("BTCUSDT", "LONG", 50000, 48000, 51500, 12, 5, "TARGET_HIT", 1.5),
    
    # Case 3: Time exit
    ("BTCUSDT", "LONG", 50000, 45000, 55000, 12, 12, "TIME_EXIT", 0.0),
    
    # Case 4: Same-candle conflict (stop wins)
    ("BTCUSDT", "LONG", 50000, 49500, 51000, 12, 1, "STOP_HIT", -0.5),
    
    # Case 5: Short direction stop
    ("BTCUSDT", "SHORT", 50000, 51000, 48500, 12, 2, "STOP_HIT", -1.0),
    
    # Case 6: Short direction target
    ("BTCUSDT", "SHORT", 50000, 51500, 49000, 12, 4, "TARGET_HIT", 1.0),
    
    # Case 7: Partial future data
    ("BTCUSDT", "LONG", 50000, 49000, 52000, 12, 0, "INVALIDATED", None),
    
    # Case 8: Horizon end (bars exhausted)
    ("BTCUSDT", "LONG", 50000, 30000, 70000, 12, 12, "HORIZON_END", None),
    
    # Case 9: Fee/slippage deduction
    ("BTCUSDT", "LONG", 50000, 49000, 51500, 12, 5, "TARGET_HIT", 1.5 - 0.062),
    
    # Case 10: Edge case - zero ATR
    ("BTCUSDT", "LONG", 50000, 50000, 50000, 12, 12, "TIME_EXIT", 0.0),
]
```

---

## Benchmark Execution

```bash
# Run all parity tests
PYTHONPATH=alphaforge/src:simulation/src:. \
    python -m pytest alphaforge/tests/test_outcome_cache/ \
    -k "parity" \
    -v \
    --tb=short

# Generate report
python scripts/parity_report.py \
    --fixtures alphaforge/tests/fixtures/parity_fixtures_v1.json \
    --cache-dir data/outcome_cache/v1 \
    --output reports/v7_lite/parity_report.md
```

---

## Success Gate

| Target | Threshold | Current Status |
|--------|-----------|----------------|
| exit_bar agreement | ≥ 99.9% | ❌ NOT TESTED |
| exit_reason agreement | ≥ 99.9% | ❌ NOT TESTED |
| net_R tolerance | < 1e-6 | ❌ NOT TESTED |
| Same-bar conflict | Pass all 10 fixtures | ❌ NOT TESTED |
| Fee/slippage parity | < 1e-6 | ❌ NOT TESTED |
| Timeout exit | Pass all 3 fixtures | ❌ NOT TESTED |

**Blocking issue:** Outcome cache P0 implementation does not yet exist.
These tests cannot be run until `alphaforge/src/alphaforge/outcome_cache/` is implemented.

---

## Escalation

If any parity target fails:

1. Log the exact candidate_id, field, expected value, and actual value
2. Classify the failure: ROUNDING / LOGIC / MISSING_FEATURE
3. If ROUNDING: adjust tolerance
4. If LOGIC: fix the outcome cache exit logic to match simulation
5. If MISSING_FEATURE: add the feature (e.g., same-candle precedence)
6. Re-run ALL parity tests after any change
7. Never skip a failing test — parity is absolute
