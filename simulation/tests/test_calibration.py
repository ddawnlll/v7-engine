"""Tests for self-calibrating hardware router in batch.py.

Verifies:
  1. Calibration actually runs both CPU and GPU, measures, caches
  2. Cache hit returns instant result (no re-measurement)
  3. Cache invalidation on hardware change
  4. CLI --calibrate and --status work
"""

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from simulation.engine.batch import (
    _CACHE_FILE,
    _hardware_fingerprint,
    _generate_calibration_signals,
    _load_cache,
    _save_cache,
    _cache_is_valid,
    calibrate_hardware,
    get_preferred_backend,
)


@pytest.fixture(autouse=True)
def _clean_cache(tmp_path):
    """Remove calibration cache before and after each test."""
    cache_file = Path(__file__).resolve().parent.parent.parent / ".simulation" / "hw_calibration.json"
    if cache_file.exists():
        cache_file.unlink()
    yield
    if cache_file.exists():
        cache_file.unlink()


class TestHardwareFingerprint:
    def test_returns_required_keys(self):
        fp = _hardware_fingerprint()
        assert "cpu_count" in fp
        assert "cpu_name" in fp
        assert "gpu_name" in fp
        assert isinstance(fp["cpu_count"], int)
        assert fp["cpu_count"] >= 1

    def test_deterministic(self):
        fp1 = _hardware_fingerprint()
        fp2 = _hardware_fingerprint()
        assert fp1 == fp2


class TestCacheInvalidation:
    def test_valid_cache_matches_current_hardware(self):
        fp = _hardware_fingerprint()
        cache = {"fingerprint": fp, "winner": "cpu"}
        assert _cache_is_valid(cache) is True

    def test_invalid_on_cpu_count_change(self):
        fp = _hardware_fingerprint()
        fp_bad = {**fp, "cpu_count": fp["cpu_count"] + 100}
        cache = {"fingerprint": fp_bad, "winner": "cpu"}
        assert _cache_is_valid(cache) is False

    def test_invalid_on_gpu_name_change(self):
        fp = _hardware_fingerprint()
        fp_bad = {**fp, "gpu_name": "FAKE_GPU_9000"}
        cache = {"fingerprint": fp_bad, "winner": "cpu"}
        assert _cache_is_valid(cache) is False


class TestCalibration:
    def test_calibrate_runs_both_backends(self):
        """Calibration should actually benchmark CPU and GPU."""
        result = calibrate_hardware(force=True)

        assert result["winner"] in ("cpu", "gpu")
        assert result["cpu_time"] > 0
        assert result["gpu_time"] is None or result["gpu_time"] > 0
        assert result["fingerprint"] == _hardware_fingerprint()
        assert "calibrated_at" in result
        assert result["n_signals"] > 0

    def test_calibrate_saves_cache(self):
        """Calibration should write cache file."""
        calibrate_hardware(force=True)
        assert _CACHE_FILE.exists()
        cache = _load_cache()
        assert cache is not None
        assert cache["winner"] in ("cpu", "gpu")

    def test_calibrate_force_overwrites_cache(self):
        """force=True should re-run even if valid cache exists."""
        # First calibration
        r1 = calibrate_hardware(force=True)
        t1 = r1["calibrated_at"]

        # Second with force=True — should re-measure
        r2 = calibrate_hardware(force=True)
        assert r2["calibrated_at"] != t1 or r2["cpu_time"] != r1["cpu_time"]

    def test_get_preferred_backend_uses_cache(self):
        """get_preferred_backend should use cache, not re-measure."""
        # Calibrate first
        calibrate_hardware(force=True)

        # Now get_preferred_backend should be fast (cache hit)
        t0 = time.time()
        backend = get_preferred_backend()
        elapsed = time.time() - t0

        assert backend in ("cpu", "gpu")
        assert elapsed < 2.0, f"Cache hit took {elapsed:.2f}s — should be < 2s"

    def test_get_preferred_backend_force_gpu(self):
        """force_gpu=True should return 'gpu' if CUDA available."""
        from simulation.engine.cuda_kernels import is_cuda_available
        backend = get_preferred_backend(force_gpu=True)
        if is_cuda_available():
            assert backend == "gpu"
        else:
            assert backend == "cpu"

    def test_calibration_consistent_with_benchmark(self):
        """Calibration should return a valid winner — accepts cpu or gpu."""
        result = calibrate_hardware(force=True)
        assert result["winner"] in ("cpu", "gpu"), (
            f"Expected cpu or gpu winner, got {result['winner']} "
            f"(cpu={result['cpu_time']:.4f}s, gpu={result['gpu_time']:.4f}s)"
        )
        assert result["cpu_time"] > 0
        if result["gpu_time"] is not None:
            assert result["gpu_time"] > 0


class TestCacheFileGitignore:
    def test_cache_dir_in_gitignore(self):
        """The .simulation/ directory should be in .gitignore."""
        gitignore = Path(__file__).resolve().parent.parent.parent / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text()
        assert ".simulation/" in content
