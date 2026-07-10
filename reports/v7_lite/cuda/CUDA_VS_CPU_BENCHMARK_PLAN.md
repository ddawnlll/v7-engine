# CUDA vs CPU Benchmark Plan — NOT NEEDED

**Status:** `SKIPPED` — benchmarks already exist in `simulation/docs/gpu_cuda_migration_plan.md`
**Generated:** 2026-07-08

---

## Why This Plan Is Not Needed

The simulation team already performed a comprehensive GPU vs CPU benchmark:

| Question | Answer |
|----------|--------|
| Was GPU vs CPU benchmarked? | **YES** — see simulation/docs/ai_summary.md §14 |
| At what scales? | 100, 1K, 10K, 100K, 1M, 2M paths |
| On what hardware? | Tesla T4 |
| Which implementation? | Numba cuda.jit + CPU-parallel Numba |
| What was the result? | **CPU 2-3x faster at ALL scales** |
| Were bugs found? | YES — 2 bugs fixed (MFE clamp, time_to_mae) |
| Is parity proven? | YES — 500 cases × 10 fields = 0.00e+00 max diff |

### Key Takeaway

Running a CUDA vs CPU benchmark would be **redundant**. The existing benchmarks
are sufficient to conclude that CUDA is not beneficial for this workload.

---

## When to Revisit

Re-run the benchmark (using the existing cuda.jit path) if:

1. **Hardware changes**: A100, H100, or custom GPU available (short-path characteristics may differ)
2. **Workload changes**: Holding periods exceed 100 bars per candidate
3. **CPU bottleneck proven**: After outcome cache is built, if profiling shows >50% time in simulation
4. **Path complexity increases**: Trailing stops, multi-barrier, MFE/MAE tracking

To re-run the existing benchmark:
```bash
python -m simulation.benchmarks.batch_simulator \
    --n-candidates 10000 100000 1000000 \
    --max-bars 12 30 100 \
    --compare-cpu-gpu
```
