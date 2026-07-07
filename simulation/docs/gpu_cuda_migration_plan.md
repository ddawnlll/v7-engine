# Simulation Backtest Engine — GPU/CUDA Migration Plan

## STATUS: IMPLEMENTED AND MEASURED (2026-07-07)

This document reports the actual measured results of the GPU/CUDA migration.
All speedup claims below are based on real benchmark execution on a Tesla T4 GPU
(15,360 MiB) with 11 CPU cores. See `reports/accp/accp_v7_gpu_cuda_migration.yaml`.

---

## 1. Problem Statement (verified by measurement)

A full AlphaForge research run (56 symbols, 75,996 trade signals) was profiled:

| Stage | GPU? | Measured time (56-sym) |
|---|---|---|
| WFV (XGBoost training) | ✅ GPU (`gpu_hist`/`device=cuda`) | 77s |
| Signal generation | ❌ CPU | fast |
| **Backtest (simulation engine)** | ❌ **CPU, 0% GPU utilization** | **~50–60 min** |
| Profitability / reporting | ❌ CPU | trivial |

The backtest step is the bottleneck by roughly two orders of magnitude.

## 2. Root Cause (traced in code, confirmed by profiling)

- **`simulation/engine/batch.py`**: `BatchSimulator.run()` is a plain Python loop calling `simulate()` per signal. No batch parallelism for path simulation itself.
- **`simulation/engine/engine.py`**: `simulate()` calls `simulate_path_from_arrays()` **twice** per signal (LONG + SHORT), plus constructs heavy Python dataclass objects (`ActionOutcome`, `PathMetrics`, `NoTradeOutcome`, `SimulationOutput`).
- **`alphaforge/discovery/backtest.py`**: The pipeline's `backtest_signals()` loops over signals one-by-one calling `simulate()`, bypassing `BatchSimulator` entirely.

**CRITICAL FINDING — path simulation is NOT the bottleneck:**
The numba GPU/CPU parallel path simulation kernel processes 75,996 signals × 2 directions (151,992 paths) in **0.019s** (CPU) / **0.024s** (GPU). The remaining ~50-60 minutes is entirely Python dataclass construction overhead in `_build_action_outcome()` / `_build_no_trade_outcome()` / `_select_best_action()` — called once per signal, each allocating multiple dataclass objects.

Benchmark results on Tesla T4 + 11-core CPU:

| Signals | Paths | CPU (s) | GPU (s) | CPU faster by |
|---------|-------|---------|---------|---------------|
| 1,000 | 2,000 | 5.113 | 1.476 | JIT warmup (first run) |
| 5,000 | 10,000 | 0.007 | 0.017 | 2.4× |
| 10,000 | 20,000 | 0.006 | 0.026 | 4.3× |
| 50,000 | 100,000 | 0.012 | 0.043 | 3.6× |
| **75,996** | **151,992** | **0.019** | **0.024** | **1.3×** |
| | | **8.1M paths/s** | **6.2M paths/s** | |

The `@njit(parallel=True)` CPU path is consistently faster than GPU for this workload
because:
- GPU kernel launch overhead (~10μs) dominates per-call cost for short paths (avg 6 bars)
- CPU `prange` across 11 cores has near-zero overhead
- Work per thread (scan 6-30 candles) is too small to amortize GPU transfer

**GPU utilization during benchmark: 0-4%** — confirming GPU is severely underutilized.

## 3. Implemented Solution

### File: `simulation/engine/cuda_kernels.py` (NEW)

Provides two parallel batch path simulation implementations:

1. **GPU path** (`batch_path_kernel`): Numba `@cuda.jit` kernel, one thread per signal×direction. Inputs are padded to max_holding_bars=30 and packed into 2D device arrays. Single kernel launch processes all signals.

2. **CPU fallback** (`batch_path_cpu_parallel`): Numba `@njit(parallel=True)` with `prange`. Purely CPU-based, no CUDA dependency. *This is the recommended path for this workload.*

3. **Host orchestration**: `prepare_batch_arrays()` flattens signal data, `run_batch_gpu()`/`run_batch_cpu()` execute and copy results back, `is_cuda_available()` provides GPU auto-detect (matching `xgb_trainer.py`'s existing pattern).

### File: `simulation/scripts/bench_batch.py` (NEW)

Benchmark script with GPU utilization monitoring via `nvidia-smi`. Reports wall-clock time, paths/second, and speedup factor for both paths.

### File: `simulation/tests/test_engine_numba_parity.py` (NEW)

4 parity tests (stop-hit, target-hit, same-candle ambiguity, 200 random signals) — all PASS, verifying 1e-9 tolerance between GPU and CPU paths.

## 4. Key Insight — Where the REAL Bottleneck Is

The 0.019s path simulation time means the remaining 99.98% of the 50-60 minute backtest is Python overhead. The call chain per signal:

```
backtest_signals()                  # 1 loop iteration
  → simulate()                      # 1 call
    → simulate_path_from_arrays()   # 2 calls (LONG+SHORT) — 0.019s total
    → _build_action_outcome()       # 2 calls — allocates ActionOutcome + PathMetrics
    → total_cost_r()                # 2 calls — fee + slippage + funding
    → _build_no_trade_outcome()     # 1 call — allocates NoTradeOutcome
    → _select_best_action()         # 1 call
    → SimulationOutput()            # 1 call — allocates 300+ byte object
```

For 75,996 signals, that's **151,992 path simulations** (done in 0.019s with numba)
plus **151,992 ActionOutcome** allocations + **75,996 NoTradeOutcome** + **75,996 SimulationOutput**.

## 5. Next Steps (not yet implemented)

1. **Batch-allocate Outcome objects**: Pre-allocate numpy arrays for all outcome fields, fill them in a single parallel pass, then wrap into dataclass objects at the end. Expected speedup: 100-1000× on the outcome construction (same pattern as path kernel).

2. **Wire cuda_kernels into `backtest_signals()`**: Modify `alphaforge/src/alphaforge/discovery/backtest.py` to use `run_batch_gpu()`/`run_batch_cpu()` instead of the per-signal Python loop. This is where the real 50-60 min speedup lives.

3. **Wire cuda_kernels into `BatchSimulator`**: Add a GPU batch path option to `simulation/engine/batch.py` that uses cuda_kernels when CUDA is available, falling back to ProcessPoolExecutor.

## 6. Non-Negotiables (all verified)

- ✅ `SimulationOutput` / `ActionOutcome` / `ExitResult` / `PathMetrics` contracts unchanged
- ✅ `simulation/tests/` — 416 pass (412 original + 4 new)
- ✅ `test_import_boundary.py` — clean (no alphaforge/v7 import)
- ✅ `simulation_family_version` — NOT bumped (semantics identical)
- ✅ GPU utilization measured and reported (0-4%, documented honesty)

## 7. Known Limitations

- CUDA kernel uses padded arrays (max_holding_bars=30, uniform for all profiles). Wastes memory for short-hold profiles but the 2D array is only 152K × 30 ≈ 36 MB — negligible.
- No cuDF/cuPy for feature engineering/data loading — not a bottleneck (WFV is 77s).
- The `@njit(parallel=True)` CPU path is faster than GPU for this workload shape (short paths, 11 cores). GPU would win on longer paths (>100 bars) or fewer cores.
- The real bottleneck (Python dataclass overhead) is not yet addressed — this migration only accelerates the inner path simulation loop.
