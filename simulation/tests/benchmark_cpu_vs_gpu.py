#!/usr/bin/env python3
"""Benchmark: CPU-parallel vs GPU path simulation across core counts."""

import os
import sys
import subprocess
import json

# Write the worker script to a temp file
WORKER_PATH = "/tmp/_bench_worker.py"
WORKER_CODE = '''import os, sys, time, json, numpy as np
import warnings
warnings.filterwarnings("ignore")

n_cores = int(os.environ["BENCH_NCORES"])
os.environ["NUMBA_NUM_THREADS"] = str(n_cores)

sys.path.insert(0, "/teamspace/studios/this_studio/v7-engine/simulation/src")
sys.path.insert(0, "/teamspace/studios/this_studio/v7-engine")
from simulation.engine.cuda_kernels import prepare_batch_arrays, run_batch_gpu, run_batch_cpu

def gen_signals(n, max_bars=30):
    rng = np.random.default_rng(42)
    sigs = []
    for _ in range(n):
        d = "LONG" if rng.random() > 0.5 else "SHORT"
        ep = rng.uniform(50, 200)
        rp = rng.uniform(0.01, 0.05)
        if d == "LONG":
            sp = ep * (1 - rp); tp = ep * (1 + rp * rng.uniform(1.5, 3.0))
            er = ep - sp
        else:
            sp = ep * (1 + rp); tp = ep * (1 - rp * rng.uniform(1.5, 3.0))
            er = sp - ep
        nb = int(rng.integers(5, max_bars + 1))
        hi = (ep + rng.uniform(0, 0.02*ep, nb)).tolist()
        lo = (ep - rng.uniform(0, 0.02*ep, nb)).tolist()
        sigs.append({"direction":d,"entry_price":ep,"stop_price":sp,"target_price":tp,
                     "entry_risk":er,"close_price":ep,"available_bars":nb,"highs":hi,"lows":lo})
    return sigs

sizes = [100, 1000, 10000, 100000, 500000, 2000000]
results = []
for n in sizes:
    sigs = gen_signals(n)
    arr = prepare_batch_arrays(sigs)
    # Warmup JIT
    for _ in range(2):
        run_batch_cpu(arr)
        run_batch_gpu(arr)
    # GPU bench
    gpu_ts = []
    for _ in range(5):
        t0 = time.perf_counter()
        run_batch_gpu(arr)
        gpu_ts.append(time.perf_counter() - t0)
    gpu_med = float(np.median(gpu_ts))
    # CPU bench
    cpu_ts = []
    for _ in range(5):
        t0 = time.perf_counter()
        run_batch_cpu(arr)
        cpu_ts.append(time.perf_counter() - t0)
    cpu_med = float(np.median(cpu_ts))
    winner = "GPU" if gpu_med < cpu_med else "CPU"
    r = {"n":n,"cores":n_cores,"cpu":cpu_med,"gpu":gpu_med,"winner":winner}
    results.append(r)
    # Print each result as JSON line
    print(json.dumps(r), flush=True)
# Print summary
print("BENCH_DONE:" + json.dumps(results))
'''


def run_bench(n_cores: int) -> list:
    env = {**os.environ, "BENCH_NCORES": str(n_cores)}
    result = subprocess.run(
        [sys.executable, WORKER_PATH],
        capture_output=True, text=True, timeout=600, env=env,
    )
    if result.returncode != 0:
        print(f"ERROR ({n_cores} cores): {result.stderr[:500]}", file=sys.stderr)
        return []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if line.startswith("BENCH_DONE:"):
            try:
                return json.loads(line[11:])
            except json.JSONDecodeError:
                pass
    return []


def main():
    # Write worker script
    with open(WORKER_PATH, "w") as f:
        f.write(WORKER_CODE)

    n_cpus = os.cpu_count()
    print(f"System: {n_cpus} logical CPUs (Intel Xeon Platinum 8259CL @ 2.50GHz)")
    print(f"GPU: Tesla T4, 15360 MiB")
    print()

    core_configs = [1, 2, 4]
    all_results = {}

    for nc in core_configs:
        print(f"--- {nc} core(s) ---", flush=True)
        results = run_bench(nc)
        for r in results:
            all_results[(r["n"], r["cores"])] = r
            sp = r["cpu"] / r["gpu"] if r["gpu"] > 0 else 0
            print(f"  N={r['n']:>10,}  CPU={r['cpu']:.4f}s  GPU={r['gpu']:.4f}s  {r['winner']} wins ({sp:.1f}x)", flush=True)
        print()

    sizes = [100, 1000, 10000, 100000, 500000, 2000000]
    print("=" * 105)
    print("SUMMARY TABLE: CPU-parallel vs GPU (median of 5 runs)")
    print("=" * 105)
    print(f"{'N':>12s} | {'CPU(1c)':>10s} | {'CPU(2c)':>10s} | {'CPU(4c)':>10s} | {'GPU':>10s} | {'Winner@4c':>10s} | {'CPU/GPU@4c':>11s}")
    print("-" * 105)

    for n in sizes:
        r1 = all_results.get((n, 1))
        r2 = all_results.get((n, 2))
        r4 = all_results.get((n, 4))
        gpu = r1["gpu"] if r1 else (r4["gpu"] if r4 else None)

        c1 = f"{r1['cpu']:.4f}s" if r1 else "N/A"
        c2 = f"{r2['cpu']:.4f}s" if r2 else "N/A"
        c4 = f"{r4['cpu']:.4f}s" if r4 else "N/A"
        g = f"{gpu:.4f}s" if gpu else "N/A"
        winner = "GPU" if (gpu and r4 and gpu < r4["cpu"]) else "CPU"
        ratio = f"{r4['cpu']/gpu:.1f}x" if (gpu and r4 and gpu > 0) else "N/A"
        print(f"{n:>12,} | {c1:>10s} | {c2:>10s} | {c4:>10s} | {g:>10s} | {winner:>10s} | {ratio:>11s}")

    # Crossover
    print("\n" + "=" * 105)
    print("CROSSOVER ANALYSIS: At what N does GPU beat CPU?")
    print("=" * 105)
    for nc in core_configs:
        core_r = [all_results.get((n, nc)) for n in sizes]
        core_r = [r for r in core_r if r]
        crossover = None
        for r in core_r:
            if r["winner"] == "GPU":
                crossover = r["n"]
                break
        if crossover:
            print(f"  {nc} core(s): GPU wins at N >= {crossover:,}")
        else:
            closest = min(core_r, key=lambda r: r["cpu"] / r["gpu"] if r["gpu"] > 0 else 999)
            ratio = closest["cpu"] / closest["gpu"] if closest["gpu"] > 0 else 0
            print(f"  {nc} core(s): CPU always wins (closest: N={closest['n']:,}, CPU is {ratio:.1f}x GPU)")

    # Final recommendation
    print("\n" + "=" * 105)
    print("ENGINEERING RECOMMENDATION")
    print("=" * 105)
    print(f"This VM: {n_cpus} logical CPUs, Tesla T4")
    print()
    for nc in core_configs:
        r2m = all_results.get((2_000_000, nc))
        if r2m:
            verdict = "GPU" if r2m["winner"] == "GPU" else "CPU"
            print(f"  @ {nc} cores, N=2M: {verdict} wins ({r2m['cpu']:.2f}s CPU vs {r2m['gpu']:.2f}s GPU)")
        r100k = all_results.get((100_000, nc))
        if r100k:
            verdict = "GPU" if r100k["winner"] == "GPU" else "CPU"
            print(f"  @ {nc} cores, N=100K: {verdict} wins ({r100k['cpu']:.2f}s CPU vs {r100k['gpu']:.2f}s GPU)")

    # Save
    out = os.path.join(os.path.dirname(__file__), "..", "benchmark_results.json")
    with open(out, "w") as f:
        json.dump({"system": {"cpus": n_cpus, "gpu": "Tesla T4 15GB", "cores_tested": core_configs},
                    "results": list(all_results.values())}, f, indent=2)
    print(f"\nResults saved to {out}")


if __name__ == "__main__":
    main()
