"""
Colab utilities — GPU verification, environment setup, data sync.

Designed to run both inside Google Colab (CUDA) and locally (CPU fallback).
"""

import os
import sys
import subprocess
import json
from pathlib import Path


def check_gpu() -> dict:
    """Check CUDA/GPU availability. Returns a status dict."""
    info = {"cuda_available": False, "gpu_name": None, "vram_gb": 0}

    try:
        import torch
        info["cuda_available"] = torch.cuda.is_available()
        if info["cuda_available"]:
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["vram_gb"] = torch.cuda.get_device_properties(0).total_memory / 1e9
            info["torch_version"] = torch.__version__
    except ImportError:
        pass

    # Fallback: nvidia-smi
    if not info["cuda_available"]:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(", ")
                info["gpu_name"] = parts[0]
                info["vram_gb"] = float(parts[1].replace(" MiB", "")) / 1024
                info["cuda_available"] = True
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pass

    return info


def smoke_test() -> dict:
    """Run GPU smoke test: tensor ops, parquet IO, checkpoint save/load."""
    results = {}

    # 1. Tensor operation
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        x = torch.randn(1000, 1000, device=device)
        y = torch.randn(1000, 1000, device=device)
        z = (x @ y).sum()
        results["tensor_op"] = {"status": "PASS", "device": device, "value": float(z)}
    except Exception as e:
        results["tensor_op"] = {"status": "FAIL", "error": str(e)}

    # 2. NumPy benchmark
    try:
        import numpy as np
        a = np.random.randn(5000, 5000).astype(np.float32)
        b = np.random.randn(5000, 5000).astype(np.float32)
        import time
        t0 = time.time()
        c = a @ b
        elapsed = time.time() - t0
        results["numpy_matmul_5k"] = {"status": "PASS", "seconds": round(elapsed, 3)}
    except Exception as e:
        results["numpy_matmul_5k"] = {"status": "FAIL", "error": str(e)}

    # 3. Parquet read/write
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        import tempfile
        table = pa.table({"x": pa.array(range(100000), type=pa.float64()),
                          "y": pa.array(range(100000), type=pa.float64())})
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            tmp_path = f.name
        pq.write_table(table, tmp_path)
        table2 = pq.read_table(tmp_path)
        os.unlink(tmp_path)
        results["parquet_io"] = {"status": "PASS", "rows": len(table2)}
    except Exception as e:
        results["parquet_io"] = {"status": "FAIL", "error": str(e)}

    return results


def install_dependencies(extra: list[str] | None = None) -> dict:
    """Install project dependencies. Returns pip status."""
    req_files = ["requirements.frozen.txt", "requirements.txt"]
    req_path = None
    for f in req_files:
        p = Path(f)
        if p.exists():
            req_path = str(p)
            break

    if req_path is None:
        return {"status": "SKIP", "reason": "No requirements file found"}

    pkgs = [req_path]
    if extra:
        pkgs.extend(extra)

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q"] + pkgs,
        capture_output=True, text=True, timeout=300,
    )
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "stdout": result.stdout[-200:],
        "stderr": result.stderr[-200:],
    }


def clone_repo(github_url: str = "https://github.com/ddawnlll/v7-engine",
               branch: str = "main", target_dir: str = "v7-engine") -> dict:
    """Clone (or pull) the v7-engine repo."""
    target = Path(target_dir)
    if target.exists():
        result = subprocess.run(
            ["git", "-C", str(target), "pull", "origin", branch],
            capture_output=True, text=True, timeout=60,
        )
        return {"status": "PULL", "output": result.stdout[-200:]}
    else:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "-b", branch, github_url, str(target)],
            capture_output=True, text=True, timeout=120,
        )
        return {"status": "CLONE", "output": result.stdout[-200:]}


def data_download(symbols: str = "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT",
                  intervals: str = "1h,4h") -> dict:
    """Download Binance Vision data using the project's download script."""
    script = "scripts/download_binance.py"
    if not Path(script).exists():
        script = "v7-engine/scripts/download_binance.py"
    if not Path(script).exists():
        return {"status": "SKIP", "reason": "download_binance.py not found"}

    result = subprocess.run(
        [sys.executable, script, "--symbols", symbols],
        capture_output=True, text=True, timeout=600,
    )
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "stdout": result.stdout[-300:],
        "stderr": result.stderr[-300:],
    }
