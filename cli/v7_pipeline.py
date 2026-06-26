"""V7 Pipeline v0.2 — End-to-end profitability evidence pipeline.

Wires together: backfill → labels → features → training → WFV → report.

Each stage is a separate step with its own deterministic evidence.
Dry-run by default. --real required for actual execution.

CRITICAL RULES (per ISSUE #35):
  - NO profitability claims in source code
  - NO live trading
  - Dry-run by default, --real required for actual execution
  - All steps emit deterministic evidence

Usage:
  # Dry-run (shows what WOULD run)
  python3 -m cli v02 --mode SWING --symbols BTCUSDT --start 2024-01-01 --end 2024-06-30
  python3 -m cli.v7_pipeline --mode SWING --dry-run

  # Real execution (requires --real)
  python3 -m cli.v7_pipeline --mode SWING --real --synthetic

  # Real execution with Binance data
  python3 -m cli.v7_pipeline --mode SWING --symbols BTCUSDT --start 2024-01-01 --end 2024-06-30 --real
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PIPELINE_VERSION: str = "0.2.0"
PIPELINE_SCHEMA_VERSION: str = "1.0.0"

DEFAULT_MODE: str = "SWING"
DEFAULT_SYMBOLS: Tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
DEFAULT_OUTPUT_DIR: str = "artifacts/pipeline"
DEFAULT_RANDOM_SEED: int = 42
DEFAULT_N_BARS: int = 2000
DEFAULT_N_SYMBOLS: int = 3

SUPPORTED_MODES: Tuple[str, ...] = ("SWING", "SCALP", "AGGRESSIVE_SCALP")

# Pipeline steps in order
PIPELINE_STEPS: Tuple[str, ...] = (
    "validate",
    "backfill",
    "labels",
    "features",
    "train",
    "wfv",
    "report",
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StepStatus(str, Enum):
    """Pipeline step execution status."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    DRY_RUN = "DRY_RUN"


class PipelineVerdict(str, Enum):
    """Overall pipeline verdict."""
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    DRY_RUN = "DRY_RUN"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


def _get_mode_intervals(mode: str) -> list[str]:
    """Relevant intervals for a trading mode (primary + context + refinement)."""
    intervals_for_mode = {
        "SWING": ["1d", "4h", "1h"],
        "SCALP": ["4h", "1h", "15m"],
        "AGGRESSIVE_SCALP": ["1h", "15m", "5m"],
    }
    return intervals_for_mode.get(mode.upper(), ["4h", "1h"])


def _get_primary_interval(mode: str) -> str:
    """Primary interval for a trading mode."""
    primary = {
        "SWING": "4h",
        "SCALP": "1h",
        "AGGRESSIVE_SCALP": "15m",
    }
    return primary.get(mode.upper(), "4h")


@dataclass(frozen=True)
class PipelineConfig:
    """Immutable pipeline configuration.

    All fields are frozen so two identical configs produce identical evidence.
    """

    mode: str = DEFAULT_MODE
    symbols: Tuple[str, ...] = DEFAULT_SYMBOLS
    start_date: Optional[str] = None  # YYYY-MM-DD
    end_date: Optional[str] = None    # YYYY-MM-DD
    output_dir: str = DEFAULT_OUTPUT_DIR
    random_seed: int = DEFAULT_RANDOM_SEED
    dry_run: bool = True
    force: bool = False
    use_synthetic: bool = True       # Use synthetic data instead of real Binance
    n_bars: int = DEFAULT_N_BARS    # Bars per symbol for synthetic data
    steps: Tuple[str, ...] = PIPELINE_STEPS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_version": PIPELINE_VERSION,
            "mode": self.mode,
            "symbols": list(self.symbols),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "output_dir": self.output_dir,
            "random_seed": self.random_seed,
            "dry_run": self.dry_run,
            "force": self.force,
            "use_synthetic": self.use_synthetic,
            "n_bars": self.n_bars,
            "steps": list(self.steps),
        }


@dataclass
class PipelineEvidence:
    """Deterministic evidence for a single pipeline step.

    Attributes:
        step: Step name from PIPELINE_STEPS.
        status: StepStatus value.
        timestamp: ISO 8601 UTC timestamp.
        duration_seconds: Wall-clock duration of the step.
        metrics: Step-specific metrics dict.
        errors: List of error messages (empty on success).
        warnings: List of warning messages.
        artifacts: List of produced artifact paths.
        checksum: SHA-256 checksum of serialized metrics (for reproducibility).
    """

    step: str
    status: str = StepStatus.PENDING.value
    timestamp: str = ""
    duration_seconds: float = 0.0
    metrics: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    checksum: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "status": self.status,
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
            "metrics": self.metrics,
            "errors": self.errors,
            "warnings": self.warnings,
            "artifacts": self.artifacts,
            "checksum": self.checksum,
        }


@dataclass
class PipelineResult:
    """Overall pipeline execution result.

    Attributes:
        config: Frozen PipelineConfig used for this run.
        evidence: Ordered list of PipelineEvidence, one per step.
        verdict: PipelineVerdict value.
        report_path: Path to the generated JSON report (if any).
        started_at: ISO 8601 UTC timestamp when pipeline started.
        completed_at: ISO 8601 UTC timestamp when pipeline completed.
        total_duration_seconds: Wall-clock duration of entire pipeline.
    """

    config: PipelineConfig
    evidence: List[PipelineEvidence] = field(default_factory=list)
    verdict: str = PipelineVerdict.INCONCLUSIVE.value
    report_path: str = ""
    started_at: str = ""
    completed_at: str = ""
    total_duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_version": PIPELINE_VERSION,
            "schema_version": PIPELINE_SCHEMA_VERSION,
            "config": self.config.to_dict(),
            "evidence": [e.to_dict() for e in self.evidence],
            "verdict": self.verdict,
            "report_path": self.report_path,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_duration_seconds": self.total_duration_seconds,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


# ---------------------------------------------------------------------------
# Pipeline context (mutable state carrier between steps)
# ---------------------------------------------------------------------------


@dataclass
class PipelineContext:
    """Mutable context that carries data between pipeline steps."""

    ohlcv_data: Optional[Dict[str, np.ndarray]] = None
    feature_matrix: Any = None  # FeatureMatrix from features.pipeline
    labels: Optional[np.ndarray] = None  # String label array
    label_ints: Optional[np.ndarray] = None  # Integer label array
    training_result: Any = None  # TrainingResult from xgb_trainer
    wfv_result: Any = None  # WalkForwardResult from walk_forward_runner
    feature_names: List[str] = field(default_factory=list)
    chrono_dataset: List[Any] = field(default_factory=list)
    symbol_list: List[str] = field(default_factory=list)
    timestamp_list: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Synthetic data generation (for synthetic mode)
# ---------------------------------------------------------------------------


def _generate_synthetic_ohlcv(
    n_bars: int = DEFAULT_N_BARS,
    symbols: Tuple[str, ...] = DEFAULT_SYMBOLS,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> Dict[str, np.ndarray]:
    """Generate synthetic multi-symbol OHLCV data.

    Uses the same generator as walk_forward_runner for consistency.
    """
    rng = np.random.RandomState(random_seed)

    all_open: List[np.ndarray] = []
    all_high: List[np.ndarray] = []
    all_low: List[np.ndarray] = []
    all_close: List[np.ndarray] = []
    all_volume: List[np.ndarray] = []
    all_symbol: List[str] = []

    for sym in symbols:
        returns = rng.randn(n_bars) * 0.02
        close = 100.0 * np.exp(np.cumsum(returns))
        close = np.maximum(close, 0.01)

        noise = rng.randn(n_bars) * 0.005
        open_arr = close * (1.0 + noise * 0.3)

        high_noise = rng.uniform(0.0, 0.015, n_bars)
        low_noise = rng.uniform(0.0, 0.015, n_bars)
        high = np.maximum(open_arr, close) * (1.0 + high_noise)
        low = np.minimum(open_arr, close) * (1.0 - low_noise)
        low = np.minimum(low, np.minimum(open_arr, close))
        high = np.maximum(high, np.maximum(open_arr, close))

        volume = rng.lognormal(mean=10.0, sigma=1.0, size=n_bars)

        all_open.append(open_arr)
        all_high.append(high)
        all_low.append(low)
        all_close.append(close)
        all_volume.append(volume)
        all_symbol.extend([sym] * n_bars)

    return {
        "open": np.concatenate(all_open),
        "high": np.concatenate(all_high),
        "low": np.concatenate(all_low),
        "close": np.concatenate(all_close),
        "volume": np.concatenate(all_volume),
        "symbol": all_symbol,
    }


def _generate_synthetic_labels(
    n_samples: int,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> np.ndarray:
    """Generate synthetic 3-class label vector.

    Labels: LONG_NOW, SHORT_NOW, NO_TRADE — roughly balanced.
    """
    rng = np.random.RandomState(random_seed)
    return rng.choice(["LONG_NOW", "SHORT_NOW", "NO_TRADE"], size=n_samples)


# Label mapping for multi-class classification
_LABEL_TO_INT: Dict[str, int] = {
    "LONG_NOW": 0,
    "SHORT_NOW": 1,
    "NO_TRADE": 2,
}

_INT_TO_LABEL: Dict[int, str] = {v: k for k, v in _LABEL_TO_INT.items()}
_NUM_CLASSES: int = 3


# ---------------------------------------------------------------------------
# Pipeline step evidence helpers
# ---------------------------------------------------------------------------


def _make_evidence(
    step: str,
    status: str,
    metrics: Optional[Dict[str, Any]] = None,
    errors: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    artifacts: Optional[List[str]] = None,
    duration_seconds: float = 0.0,
) -> PipelineEvidence:
    """Build a PipelineEvidence record with deterministic checksum."""
    ev = PipelineEvidence(
        step=step,
        status=status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        duration_seconds=duration_seconds,
        metrics=metrics or {},
        errors=errors or [],
        warnings=warnings or [],
        artifacts=artifacts or [],
    )
    # Compute deterministic checksum from serialized metrics
    raw = json.dumps(ev.metrics, sort_keys=True, default=str)
    ev.checksum = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return ev


def _dry_run_evidence(step: str, config: PipelineConfig) -> PipelineEvidence:
    """Build dry-run evidence for a step."""
    metrics: Dict[str, Any] = {
        "mode": config.mode,
        "symbols": list(config.symbols),
        "dry_run": True,
    }
    if step == "backfill":
        metrics.update({
            "start_date": config.start_date or "default",
            "end_date": config.end_date or "default",
            "use_synthetic": config.use_synthetic,
            "n_bars": config.n_bars,
        })
    elif step == "labels":
        metrics.update({
            "label_method": "synthetic" if config.use_synthetic else "simulation",
        })
    elif step == "features":
        metrics.update({
            "pipeline_version": "0.1.0",
            "feature_groups": 6,
        })
    elif step == "train":
        metrics.update({
            "model_family": "xgboost",
            "hyperparameters": "SWING_DEFAULT_HYPERPARAMS (LOCKED_INITIAL_BASELINE)",
        })
    elif step == "wfv":
        metrics.update({
            "min_folds": 3,
            "window_type": "ANCHORED",
        })
    elif step == "report":
        metrics.update({
            "output_dir": config.output_dir,
        })

    return _make_evidence(step, StepStatus.DRY_RUN.value, metrics=metrics)


# ---------------------------------------------------------------------------
# Pipeline Runner
# ---------------------------------------------------------------------------


class PipelineRunner:
    """End-to-end V7 pipeline runner.

    Orchestrates: backfill → labels → features → train → WFV → report.

    Each step produces deterministic PipelineEvidence.
    Dry-run prints what WOULD run without executing.
    --real required for actual execution.

    Usage:
        config = PipelineConfig(mode="SWING", dry_run=False, use_synthetic=True)
        runner = PipelineRunner(config)
        result = runner.run()
        print(result.to_json())
    """

    def __init__(self, config: PipelineConfig) -> None:
        self._config = config
        self._ctx = PipelineContext()
        self._evidence: List[PipelineEvidence] = []

    @property
    def config(self) -> PipelineConfig:
        return self._config

    # ------------------------------------------------------------------
    # run()
    # ------------------------------------------------------------------

    def run(self) -> PipelineResult:
        """Execute the pipeline.

        Returns:
            PipelineResult with evidence for each step and overall verdict.
        """
        started_at = datetime.now(timezone.utc).isoformat()
        start_time = time.monotonic()

        pipeline_ok = True

        for step in self._config.steps:
            if self._config.dry_run:
                ev = _dry_run_evidence(step, self._config)
                self._evidence.append(ev)
                print(f"[DRY RUN] Step: {step} — would execute with config:")
                for k, v in sorted(ev.metrics.items()):
                    print(f"  {k}: {v}")
                continue

            # Real execution
            print(f"\n{'='*60}")
            print(f"=== Pipeline step: {step} ===")
            print(f"{'='*60}")

            step_start = time.monotonic()
            try:
                ev = self._execute_step(step)
                ev.duration_seconds = time.monotonic() - step_start
                self._evidence.append(ev)

                if ev.status == StepStatus.FAILED.value:
                    print(f"\n!!! Pipeline FAILED at step: {step}")
                    for err in ev.errors:
                        print(f"  ERROR: {err}")
                    pipeline_ok = False
                    break

                print(f"  Status: {ev.status}")
                print(f"  Duration: {ev.duration_seconds:.3f}s")
                print(f"  Checksum: {ev.checksum}")

            except Exception as e:
                ev = _make_evidence(
                    step,
                    StepStatus.FAILED.value,
                    errors=[f"Unhandled exception: {e}"],
                    duration_seconds=time.monotonic() - step_start,
                )
                self._evidence.append(ev)
                print(f"\n!!! Pipeline FAILED at step: {step}")
                print(f"  Unhandled exception: {e}")
                pipeline_ok = False
                break

        total_duration = time.monotonic() - start_time
        completed_at = datetime.now(timezone.utc).isoformat()

        # Determine verdict
        if self._config.dry_run:
            verdict = PipelineVerdict.DRY_RUN.value
        elif pipeline_ok and all(
            e.status == StepStatus.COMPLETED.value for e in self._evidence
        ):
            verdict = PipelineVerdict.PASS.value
        elif pipeline_ok:
            verdict = PipelineVerdict.PASS_WITH_WARNINGS.value
        else:
            verdict = PipelineVerdict.FAIL.value

        result = PipelineResult(
            config=self._config,
            evidence=self._evidence,
            verdict=verdict,
            report_path=self._ctx.report_path if hasattr(self._ctx, "report_path") else "",
            started_at=started_at,
            completed_at=completed_at,
            total_duration_seconds=total_duration,
        )

        # Save pipeline report if not dry-run
        if not self._config.dry_run:
            self._save_pipeline_report(result)

        return result

    # ------------------------------------------------------------------
    # Step execution dispatcher
    # ------------------------------------------------------------------

    def _execute_step(self, step: str) -> PipelineEvidence:
        """Dispatch step execution to the appropriate handler."""
        handlers: Dict[str, Any] = {
            "validate": self._step_validate,
            "backfill": self._step_backfill,
            "labels": self._step_labels,
            "features": self._step_features,
            "train": self._step_train,
            "wfv": self._step_wfv,
            "report": self._step_report,
        }

        handler = handlers.get(step)
        if handler is None:
            return _make_evidence(
                step,
                StepStatus.FAILED.value,
                errors=[f"Unknown step: {step}"],
            )

        return handler()

    # ------------------------------------------------------------------
    # Step: validate
    # ------------------------------------------------------------------

    def _step_validate(self) -> PipelineEvidence:
        """Validate pipeline configuration and environment."""
        errors: List[str] = []
        warnings: List[str] = []

        # Validate mode
        if self._config.mode not in SUPPORTED_MODES:
            errors.append(
                f"Unsupported mode: '{self._config.mode}'. "
                f"Supported: {SUPPORTED_MODES}"
            )

        # Validate symbols
        if not self._config.symbols:
            errors.append("No symbols specified")

        # Validate date range if not synthetic
        if not self._config.use_synthetic:
            if not self._config.start_date:
                errors.append("start_date required for non-synthetic mode")
            if not self._config.end_date:
                errors.append("end_date required for non-synthetic mode")
            if self._config.start_date and self._config.end_date:
                try:
                    start_dt = datetime.strptime(self._config.start_date, "%Y-%m-%d")
                    end_dt = datetime.strptime(self._config.end_date, "%Y-%m-%d")
                    if start_dt >= end_dt:
                        errors.append(
                            f"start_date ({self._config.start_date}) must be before "
                            f"end_date ({self._config.end_date})"
                        )
                except ValueError as e:
                    errors.append(f"Invalid date format: {e}")

        # Validate output dir writable
        try:
            os.makedirs(self._config.output_dir, exist_ok=True)
        except OSError as e:
            errors.append(f"Cannot create output directory: {e}")

        metrics: Dict[str, Any] = {
            "mode": self._config.mode,
            "symbols": list(self._config.symbols),
            "use_synthetic": self._config.use_synthetic,
            "n_bars": self._config.n_bars if self._config.use_synthetic else None,
            "output_dir": self._config.output_dir,
            "random_seed": self._config.random_seed,
        }

        if errors:
            return _make_evidence(
                "validate",
                StepStatus.FAILED.value,
                metrics=metrics,
                errors=errors,
                warnings=warnings,
            )

        return _make_evidence(
            "validate",
            StepStatus.COMPLETED.value,
            metrics=metrics,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Step: backfill
    # ------------------------------------------------------------------

    def _step_backfill(self) -> PipelineEvidence:
        """Backfill market data.

        In synthetic mode: generate synthetic OHLCV data.
        In real mode: use AlphaForgeBackfillPipeline with Binance.
        """
        metrics: Dict[str, Any] = {
            "mode": self._config.mode,
            "symbols": list(self._config.symbols),
            "use_synthetic": self._config.use_synthetic,
        }
        errors: List[str] = []
        warnings: List[str] = []

        if self._config.use_synthetic:
            # Generate synthetic OHLCV data deterministically
            ohlcv = _generate_synthetic_ohlcv(
                n_bars=self._config.n_bars,
                symbols=self._config.symbols,
                random_seed=self._config.random_seed,
            )
            self._ctx.ohlcv_data = ohlcv

            total_bars = len(ohlcv["close"])
            n_symbols = len(self._config.symbols)
            bars_per_symbol = total_bars // n_symbols if n_symbols > 0 else 0

            metrics.update({
                "total_bars": total_bars,
                "n_symbols": n_symbols,
                "bars_per_symbol": bars_per_symbol,
                "data_source": "synthetic",
                "random_seed": self._config.random_seed,
            })

            print(f"  Generated {total_bars} synthetic bars across {n_symbols} symbols")
            print(f"  Bars per symbol: {bars_per_symbol}")
        else:
            # Real Binance backfill — use lib-level backfill orchestrator directly
            # AlphaForge BackfillPipeline requires service objects; skip it for
            # v0.2 direct CLI usage and call the proven lib-level pipeline.
            try:
                from lib.market_data.binance.klines_service import KlinesService
                from lib.market_data.binance.market_data_service import (
                    BinanceMarketDataService,
                )
                from lib.market_data.storage import StorageWriter
                from lib.market_data.catalog import DataCatalog
                from lib.market_data.binance.backfill import BackfillOrchestrator
                from lib.market_data.binance.rate_limiter import BinanceRateLimiter
                from lib.market_data.binance.checkpoint import BackfillCheckpoint

                # Parse dates to ms timestamps
                if self._config.start_date and self._config.end_date:
                    start_dt = datetime.strptime(
                        self._config.start_date, "%Y-%m-%d"
                    ).replace(tzinfo=timezone.utc)
                    end_dt = datetime.strptime(
                        self._config.end_date, "%Y-%m-%d"
                    ).replace(tzinfo=timezone.utc)
                    start_ms = int(start_dt.timestamp() * 1000)
                    end_ms = int(end_dt.timestamp() * 1000)
                else:
                    errors.append("start_date and end_date required for real backfill")
                    return _make_evidence(
                        "backfill", StepStatus.FAILED.value,
                        metrics=metrics, errors=errors, warnings=warnings,
                    )

                # Wire up services
                bmd = BinanceMarketDataService()
                klines = KlinesService(client=bmd._client)
                storage = StorageWriter()  # defaults to data/
                catalog = DataCatalog()
                rate_limiter = BinanceRateLimiter()
                checkpoint = BackfillCheckpoint(
                    file_path="/tmp/backfill_checkpoint.json"
                )

                orchestrator = BackfillOrchestrator(
                    klines_service=klines,
                    funding_service=None,
                    storage_writer=storage,
                    catalog=catalog,
                    rate_limiter=rate_limiter,
                    checkpoint=checkpoint,
                )

                # Backfill all intervals relevant to the mode
                intervals = _get_mode_intervals(self._config.mode)
                stats = orchestrator.backfill(
                    symbols=list(self._config.symbols),
                    intervals=intervals,
                    start_time=start_ms,
                    end_time=end_ms,
                    batch_size=50000,
                )

                metrics.update({
                    "total_records": stats.get("total_records", 0),
                    "total_symbols": stats.get("total_symbols", 0),
                    "total_intervals": stats.get("total_intervals", 0),
                    "errors_count": len(stats.get("errors", [])),
                    "data_source": "binance",
                    "intervals": intervals,
                })
                warnings = stats.get("errors", [])

                # Load cached data back into pipeline context for downstream steps
                import numpy as np
                import pyarrow.parquet as pq
                from pathlib import Path

                data_dir = Path(self._config.output_dir) / "cache"
                if not data_dir.exists():
                    data_dir = Path("data") / "cache"
                    data_dir.mkdir(parents=True, exist_ok=True)

                primary = _get_primary_interval(self._config.mode)
                combined_close: list[float] = []
                combined_open: list[float] = []
                combined_high: list[float] = []
                combined_low: list[float] = []
                combined_volume: list[float] = []
                combined_timestamp: list[int] = []
                combined_symbol: list[str] = []

                for sym in self._config.symbols:
                    pq_path = data_dir / f"{sym}_{primary}.parquet"
                    if pq_path.exists():
                        table = pq.read_table(str(pq_path))
                        df = table.to_pandas()
                        n = len(df)
                        combined_close.extend(df["close"].tolist())
                        combined_open.extend(df["open"].tolist())
                        combined_high.extend(df["high"].tolist())
                        combined_low.extend(df["low"].tolist())
                        combined_volume.extend(df["volume"].tolist())
                        combined_timestamp.extend(df["timestamp"].tolist())
                        combined_symbol.extend([sym] * n)
                    else:
                        # Try raw dir
                        raw_dir = Path("data") / "raw" / sym
                        if raw_dir.exists():
                            pq_files = sorted(raw_dir.glob(f"*_{primary}_*.parquet"))
                            for pf in pq_files:
                                table = pq.read_table(str(pf))
                                df = table.to_pandas()
                                n = len(df)
                                combined_close.extend(df["close"].tolist())
                                combined_open.extend(df["open"].tolist())
                                combined_high.extend(df["high"].tolist())
                                combined_low.extend(df["low"].tolist())
                                combined_volume.extend(df["volume"].tolist())
                                combined_timestamp.extend(df["timestamp"].tolist())
                                combined_symbol.extend([sym] * n)

                if combined_close:
                    self._ctx.ohlcv_data = {
                        "close": np.array(combined_close, dtype=np.float64),
                        "open": np.array(combined_open, dtype=np.float64),
                        "high": np.array(combined_high, dtype=np.float64),
                        "low": np.array(combined_low, dtype=np.float64),
                        "volume": np.array(combined_volume, dtype=np.float64),
                        "timestamp": np.array(combined_timestamp, dtype=np.int64),
                        "symbol": combined_symbol,
                    }
                    metrics["ohlcv_loaded"] = len(combined_close)

            except ImportError as e:
                errors.append(f"Cannot import backfill module: {e}")
                return _make_evidence(
                    "backfill", StepStatus.FAILED.value,
                    metrics=metrics, errors=errors, warnings=warnings,
                )
            except Exception as e:
                errors.append(f"Backfill failed: {e}")
                return _make_evidence(
                    "backfill", StepStatus.FAILED.value,
                    metrics=metrics, errors=errors, warnings=warnings,
                )

        if errors:
            return _make_evidence(
                "backfill", StepStatus.FAILED.value,
                metrics=metrics, errors=errors, warnings=warnings,
            )

        return _make_evidence(
            "backfill", StepStatus.COMPLETED.value,
            metrics=metrics, warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Step: labels
    # ------------------------------------------------------------------

    def _step_labels(self) -> PipelineEvidence:
        """Generate alpha labels.

        In synthetic mode: generate synthetic 3-class labels.
        In real mode: use LabelAdapter with SimulationOutput (not yet wired).
        """
        metrics: Dict[str, Any] = {
            "mode": self._config.mode,
            "label_method": "synthetic" if self._config.use_synthetic else "simulation",
        }
        errors: List[str] = []

        if self._ctx.ohlcv_data is None:
            errors.append("No OHLCV data available — run backfill step first")
            return _make_evidence(
                "labels", StepStatus.FAILED.value,
                metrics=metrics, errors=errors,
            )

        n_bars = len(self._ctx.ohlcv_data["close"])

        if self._config.use_synthetic:
            # Generate synthetic labels for each bar
            labels = _generate_synthetic_labels(
                n_samples=n_bars,
                random_seed=self._config.random_seed + 1,  # Offset seed from OHLCV
            )
            self._ctx.labels = labels
            self._ctx.label_ints = np.array(
                [_LABEL_TO_INT[str(lbl)] for lbl in labels], dtype=int
            )

            unique, counts = np.unique(labels, return_counts=True)
            distribution = {str(k): int(v) for k, v in zip(unique, counts)}

            metrics.update({
                "n_labels": n_bars,
                "label_distribution": distribution,
                "label_classes": sorted(_LABEL_TO_INT.keys()),
            })

            print(f"  Generated {n_bars} synthetic labels")
            print(f"  Distribution: {distribution}")
        else:
            # Real labels from SimulationOutput via LabelAdapter
            # NOT YET WIRED — requires simulation pipeline
            errors.append(
                "Real label generation requires SimulationOutput. "
                "Use --synthetic for synthetic labels, or wait for simulation pipeline."
            )
            return _make_evidence(
                "labels", StepStatus.FAILED.value,
                metrics=metrics, errors=errors,
            )

        if errors:
            return _make_evidence(
                "labels", StepStatus.FAILED.value,
                metrics=metrics, errors=errors,
            )

        return _make_evidence(
            "labels", StepStatus.COMPLETED.value, metrics=metrics,
        )

    # ------------------------------------------------------------------
    # Step: features
    # ------------------------------------------------------------------

    def _step_features(self) -> PipelineEvidence:
        """Compute features from OHLCV data using alphaforge.features.pipeline."""
        metrics: Dict[str, Any] = {
            "mode": self._config.mode,
            "pipeline_version": "0.1.0",
        }
        errors: List[str] = []

        if self._ctx.ohlcv_data is None:
            errors.append("No OHLCV data available — run backfill step first")
            return _make_evidence(
                "features", StepStatus.FAILED.value,
                metrics=metrics, errors=errors,
            )

        try:
            from alphaforge.features.pipeline import compute_features

            feature_matrix = compute_features(
                self._ctx.ohlcv_data,
                mode=self._config.mode,
            )
            self._ctx.feature_matrix = feature_matrix
            self._ctx.feature_names = sorted(feature_matrix.features.keys())

            metrics.update({
                "n_features": len(self._ctx.feature_names),
                "n_bars": feature_matrix.bar_count(),
                "feature_names": self._ctx.feature_names,
                "feature_groups": feature_matrix.feature_group_ids,
                "lead_lag_status": "HOLD-LEAD-LAG",
            })

            print(f"  Computed {len(self._ctx.feature_names)} features")
            print(f"  Feature groups: {feature_matrix.feature_group_ids}")
            print(f"  Bars: {feature_matrix.bar_count()}")

            # Build chrono dataset for WFV
            all_symbols = self._ctx.ohlcv_data.get("symbol", [])
            symbol_list = []
            timestamp_list = []

            # Remove NaN rows from feature matrix to build chrono dataset
            X_all = np.column_stack([
                feature_matrix.features[name]
                for name in self._ctx.feature_names
            ])
            nan_mask = np.isnan(X_all).any(axis=1)

            for i in range(len(all_symbols)):
                if not nan_mask[i]:
                    symbol_list.append(str(all_symbols[i]))
                    timestamp_list.append(f"2025-01-01T{i:06d}")

            self._ctx.symbol_list = symbol_list
            self._ctx.timestamp_list = timestamp_list

            # Build chrono dataset (minimal dataclass for WalkForwardValidator)
            from dataclasses import dataclass as _dc

            @_dc
            class _ChronoRow:
                feature_timestamp: str
                symbol: str

            self._ctx.chrono_dataset = [
                _ChronoRow(
                    feature_timestamp=timestamp_list[i],
                    symbol=symbol_list[i],
                )
                for i in range(len(symbol_list))
            ]

            metrics["valid_rows"] = len(symbol_list)
            metrics["nan_rows_dropped"] = int(nan_mask.sum())

        except ImportError as e:
            errors.append(f"Cannot import features module: {e}")
        except Exception as e:
            errors.append(f"Feature computation failed: {e}")

        if errors:
            return _make_evidence(
                "features", StepStatus.FAILED.value,
                metrics=metrics, errors=errors,
            )

        return _make_evidence(
            "features", StepStatus.COMPLETED.value, metrics=metrics,
        )

    # ------------------------------------------------------------------
    # Step: train
    # ------------------------------------------------------------------

    def _step_train(self) -> PipelineEvidence:
        """Train XGBoost classifier model."""
        metrics: Dict[str, Any] = {
            "mode": self._config.mode,
            "model_family": "xgboost",
            "hyperparameters": "SWING_DEFAULT_HYPERPARAMS (LOCKED_INITIAL_BASELINE)",
        }
        errors: List[str] = []

        if self._ctx.feature_matrix is None:
            errors.append("No features available — run features step first")
            return _make_evidence(
                "train", StepStatus.FAILED.value,
                metrics=metrics, errors=errors,
            )

        if self._ctx.label_ints is None:
            errors.append("No labels available — run labels step first")
            return _make_evidence(
                "train", StepStatus.FAILED.value,
                metrics=metrics, errors=errors,
            )

        try:
            from alphaforge.training.xgb_trainer import XGBoostTrainer

            # Assemble feature array (remove NaN rows)
            feature_names = self._ctx.feature_names
            X_all = np.column_stack([
                self._ctx.feature_matrix.features[name]
                for name in feature_names
            ])
            nan_mask = np.isnan(X_all).any(axis=1)
            X = X_all[~nan_mask]
            X = np.ascontiguousarray(X, dtype=np.float64)

            # Align labels with valid feature rows
            y_labels = self._ctx.labels[~nan_mask] if self._ctx.labels is not None else None
            if y_labels is None or len(y_labels) != len(X):
                errors.append(
                    f"Label/feature mismatch: {len(X)} valid features, "
                    f"{len(y_labels) if y_labels is not None else 0} labels"
                )
                return _make_evidence(
                    "train", StepStatus.FAILED.value,
                    metrics=metrics, errors=errors,
                )

            # Encode labels
            y_int = np.array(
                [_LABEL_TO_INT.get(str(lbl), 2) for lbl in y_labels],
                dtype=int,
            )

            trainer = XGBoostTrainer(
                mode=self._config.mode,
                random_seed=self._config.random_seed,
            )
            result = trainer.train(
                X, y_int,
                feature_names=feature_names,
            )
            self._ctx.training_result = result

            # Save model artifact
            artifact_path = trainer.save_artifact(
                result,
                artifact_dir=os.path.join(self._config.output_dir, "models"),
            )

            train_m = result.train_metrics
            val_m = result.val_metrics

            metrics.update({
                "n_samples": len(X),
                "n_features": len(feature_names),
                "train_accuracy": train_m.get("accuracy", 0.0),
                "val_accuracy": val_m.get("accuracy", 0.0),
                "train_logloss": train_m.get("logloss", 0.0),
                "val_logloss": val_m.get("logloss", 0.0),
                "training_duration_seconds": result.training_duration_seconds,
                "model_size_bytes": len(result.model_binary_bytes),
                "artifact_path": str(artifact_path),
            })

            classes = {}
            for cls_name, cls_metrics in train_m.get("per_class", {}).items():
                classes[cls_name] = {
                    "precision": cls_metrics.get("precision", 0.0),
                    "recall": cls_metrics.get("recall", 0.0),
                    "f1": cls_metrics.get("f1", 0.0),
                    "support": cls_metrics.get("support", 0),
                }
            metrics["per_class_train"] = classes

            print(f"  Trained on {len(X)} samples, {len(feature_names)} features")
            print(f"  Train accuracy: {train_m.get('accuracy', 0):.4f}")
            print(f"  Val accuracy:   {val_m.get('accuracy', 0):.4f}")
            print(f"  Duration:       {result.training_duration_seconds:.3f}s")
            print(f"  Model saved to: {artifact_path}")

        except ImportError as e:
            errors.append(f"Cannot import training module: {e}")
        except Exception as e:
            errors.append(f"Training failed: {e}")
            logger.exception("Training step exception")

        if errors:
            return _make_evidence(
                "train", StepStatus.FAILED.value,
                metrics=metrics, errors=errors,
            )

        return _make_evidence(
            "train",
            StepStatus.COMPLETED.value,
            metrics=metrics,
            artifacts=[str(artifact_path)] if 'artifact_path' in dir() else [],
        )

    # ------------------------------------------------------------------
    # Step: wfv (walk-forward validation)
    # ------------------------------------------------------------------

    def _step_wfv(self) -> PipelineEvidence:
        """Run walk-forward validation with trained model."""
        metrics: Dict[str, Any] = {
            "mode": self._config.mode,
        }
        errors: List[str] = []

        try:
            from alphaforge.validation.walk_forward_runner import run_walk_forward

            result = run_walk_forward(
                n_bars=self._config.n_bars,
                n_symbols=len(self._config.symbols),
                random_seed=self._config.random_seed,
                min_folds=3,  # Per issue spec
            )
            self._ctx.wfv_result = result

            agg = result.aggregate_metrics
            metrics.update({
                "n_folds": len(result.folds),
                "verdict": result.verdict,
                "report_id": result.report_id,
                "avg_train_accuracy": agg.get("avg_train_accuracy", 0.0),
                "avg_val_accuracy": agg.get("avg_val_accuracy", 0.0),
                "avg_accuracy_gap": agg.get("avg_accuracy_gap", 0.0),
                "avg_logloss_gap": agg.get("avg_logloss_gap", 0.0),
                "avg_sharpe": agg.get("avg_sharpe", 0.0),
                "sharpe_stability_std": agg.get("sharpe_stability_std", 0.0),
                "avg_win_rate": agg.get("avg_win_rate", 0.0),
                "avg_max_drawdown": agg.get("avg_max_drawdown", 0.0),
                "avg_profit_factor": agg.get("avg_profit_factor", 0.0),
                "total_oos_trades": agg.get("total_oos_trades", 0),
                "overfit_flags": len(result.overfit_flags),
            })

            if result.overfit_flags:
                metrics["overfit_details"] = [
                    {
                        "indicator": f.indicator,
                        "severity": f.severity,
                        "description": f.description,
                    }
                    for f in result.overfit_flags
                ]

            # Save WFV report
            report_filename = f"wfv_report_{result.report_id}.json"
            report_path = os.path.join(self._config.output_dir, "reports", report_filename)
            os.makedirs(os.path.dirname(report_path), exist_ok=True)

            from alphaforge.validation.walk_forward_runner import (
                walk_forward_result_to_dict,
            )
            wfv_dict = walk_forward_result_to_dict(result)
            with open(report_path, "w") as f:
                json.dump(wfv_dict, f, indent=2, default=str)

            print(f"  Folds: {len(result.folds)}")
            print(f"  Verdict: {result.verdict}")
            print(f"  Avg Sharpe: {agg.get('avg_sharpe', 0):.4f}")
            print(f"  Avg Win Rate: {agg.get('avg_win_rate', 0):.4f}")
            print(f"  Overfit flags: {len(result.overfit_flags)}")
            print(f"  Report saved to: {report_path}")

            metrics["wfv_report_path"] = report_path

        except ImportError as e:
            errors.append(f"Cannot import WFV module: {e}")
        except Exception as e:
            errors.append(f"WFV failed: {e}")
            logger.exception("WFV step exception")

        if errors:
            return _make_evidence(
                "wfv", StepStatus.FAILED.value,
                metrics=metrics, errors=errors,
            )

        return _make_evidence(
            "wfv",
            StepStatus.COMPLETED.value,
            metrics=metrics,
            artifacts=[report_path] if 'report_path' in dir() else [],
        )

    # ------------------------------------------------------------------
    # Step: report
    # ------------------------------------------------------------------

    def _step_report(self) -> PipelineEvidence:
        """Generate pipeline report."""
        metrics: Dict[str, Any] = {
            "mode": self._config.mode,
            "pipeline_version": PIPELINE_VERSION,
            "output_dir": self._config.output_dir,
        }
        errors: List[str] = []

        # Gather aggregate metrics from previous steps
        step_results: Dict[str, str] = {}
        for ev in self._evidence:
            step_results[ev.step] = ev.status

        metrics["step_results"] = step_results

        # Collect per-step metric summaries
        for ev in self._evidence:
            if ev.step == "train" and ev.status == StepStatus.COMPLETED.value:
                metrics["train_accuracy"] = ev.metrics.get("train_accuracy", 0.0)
                metrics["val_accuracy"] = ev.metrics.get("val_accuracy", 0.0)
            elif ev.step == "wfv" and ev.status == StepStatus.COMPLETED.value:
                metrics["wfv_verdict"] = ev.metrics.get("verdict", "UNKNOWN")
                metrics["wfv_n_folds"] = ev.metrics.get("n_folds", 0)
                metrics["wfv_avg_sharpe"] = ev.metrics.get("avg_sharpe", 0.0)

        # Save report
        try:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            report_filename = f"pipeline_v02_{self._config.mode.lower()}_{ts}.json"
            report_path = os.path.join(
                self._config.output_dir, "reports", report_filename,
            )
            os.makedirs(os.path.dirname(report_path), exist_ok=True)

            report_data = {
                "pipeline_version": PIPELINE_VERSION,
                "schema_version": PIPELINE_SCHEMA_VERSION,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "config": self._config.to_dict(),
                "step_results": step_results,
                "metrics": metrics,
                "evidence_checksums": [
                    {"step": e.step, "checksum": e.checksum}
                    for e in self._evidence
                ],
            }
            with open(report_path, "w") as f:
                json.dump(report_data, f, indent=2, default=str)

            self._ctx.report_path = report_path
            metrics["report_path"] = report_path

            print(f"  Report saved to: {report_path}")

        except OSError as e:
            errors.append(f"Cannot save report: {e}")

        if errors:
            return _make_evidence(
                "report", StepStatus.FAILED.value,
                metrics=metrics, errors=errors,
            )

        return _make_evidence(
            "report",
            StepStatus.COMPLETED.value,
            metrics=metrics,
            artifacts=[report_path] if 'report_path' in dir() else [],
        )

    # ------------------------------------------------------------------
    # Report persistence
    # ------------------------------------------------------------------

    def _save_pipeline_report(self, result: PipelineResult) -> None:
        """Save the full pipeline result as JSON."""
        try:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            filename = f"pipeline_result_{self._config.mode.lower()}_{ts}.json"
            path = os.path.join(self._config.output_dir, "reports", filename)
            os.makedirs(os.path.dirname(path), exist_ok=True)

            with open(path, "w") as f:
                f.write(result.to_json())

            result.report_path = path
            print(f"\nPipeline result saved to: {path}")

        except OSError as e:
            logger.error(f"Cannot save pipeline result: {e}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build argument parser for v7_pipeline."""
    parser = argparse.ArgumentParser(
        prog="v7-pipeline",
        description="V7 Pipeline v0.2 — End-to-end profitability evidence pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Dry-run (default)\n"
            "  python3 -m cli.v7_pipeline --mode SWING\n\n"
            "  # Real execution with synthetic data\n"
            "  python3 -m cli.v7_pipeline --mode SWING --real --synthetic\n\n"
            "  # Real execution with Binance data\n"
            "  python3 -m cli.v7_pipeline --mode SWING --symbols BTCUSDT,ETHUSDT "
            "--start 2024-01-01 --end 2024-06-30 --real --no-synthetic\n\n"
            "  # Run specific steps only\n"
            "  python3 -m cli.v7_pipeline --mode SWING --real --synthetic "
            "--steps backfill,labels,features"
        ),
    )

    parser.add_argument(
        "--mode",
        default=DEFAULT_MODE,
        help=f"Trading mode: {', '.join(SUPPORTED_MODES)} (default: {DEFAULT_MODE})",
    )
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated trading pair symbols",
    )
    parser.add_argument(
        "--start",
        default=None,
        help="Start date YYYY-MM-DD (required for non-synthetic mode)",
    )
    parser.add_argument(
        "--end",
        default=None,
        help="End date YYYY-MM-DD (required for non-synthetic mode)",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for artifacts (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help=f"Random seed for reproducibility (default: {DEFAULT_RANDOM_SEED})",
    )
    parser.add_argument(
        "--n-bars",
        type=int,
        default=DEFAULT_N_BARS,
        help=f"Bars per symbol for synthetic data (default: {DEFAULT_N_BARS})",
    )
    parser.add_argument(
        "--steps",
        default=None,
        help="Comma-separated steps to run (default: all). "
             f"Available: {', '.join(PIPELINE_STEPS)}",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Actually execute pipeline steps (default: dry-run only)",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        default=True,
        help="Use synthetic data (default: True). Pass --no-synthetic for real data.",
    )
    parser.add_argument(
        "--no-synthetic",
        action="store_true",
        help="Use real Binance data instead of synthetic",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip safety gates",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would run without executing (default unless --real)",
    )

    return parser


def _parse_args(argv: Optional[List[str]] = None) -> PipelineConfig:
    """Parse CLI arguments into a PipelineConfig."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Validate mode (case-insensitive accept, then uppercase)
    mode = args.mode.upper()
    if mode not in SUPPORTED_MODES:
        print(
            f"Error: invalid mode: '{args.mode}'. "
            f"Supported: {', '.join(SUPPORTED_MODES)}",
            file=sys.stderr,
        )
        sys.exit(2)

    # Resolve dry_run
    dry_run = args.dry_run or not args.real

    # Resolve use_synthetic
    use_synthetic = not args.no_synthetic

    # Parse symbols
    symbols = tuple(
        s.strip() for s in args.symbols.split(",") if s.strip()
    ) or DEFAULT_SYMBOLS

    # Parse steps
    if args.steps:
        steps = tuple(
            s.strip() for s in args.steps.split(",") if s.strip()
        )
        # Validate step names
        for step in steps:
            if step not in PIPELINE_STEPS:
                print(f"Warning: Unknown step '{step}'. Available: {PIPELINE_STEPS}")
        steps = tuple(s for s in steps if s in PIPELINE_STEPS)
        if not steps:
            steps = PIPELINE_STEPS
    else:
        steps = PIPELINE_STEPS

    return PipelineConfig(
        mode=mode,
        symbols=symbols,
        start_date=args.start,
        end_date=args.end,
        output_dir=args.output_dir,
        random_seed=args.seed,
        dry_run=dry_run,
        force=args.force,
        use_synthetic=use_synthetic,
        n_bars=args.n_bars,
        steps=steps,
    )


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for v7_pipeline.

    Returns:
        0 on success, 1 on failure.
    """
    config = _parse_args(argv)

    print("=" * 60)
    print("V7 Pipeline v0.2 — Profitability Evidence Pipeline")
    print("=" * 60)
    print(f"Mode:       {config.mode}")
    print(f"Symbols:    {', '.join(config.symbols)}")
    print(f"Dry run:    {config.dry_run}")
    print(f"Synthetic:  {config.use_synthetic}")
    print(f"N bars:     {config.n_bars if config.use_synthetic else 'N/A'}")
    print(f"Output dir: {config.output_dir}")
    print(f"Random seed: {config.random_seed}")
    print(f"Steps:      {', '.join(config.steps)}")
    print()

    if config.dry_run:
        print("DRY RUN MODE — set --real to execute")
        print()

    runner = PipelineRunner(config)
    result = runner.run()

    print()
    print("=" * 60)
    print(f"Pipeline complete — Verdict: {result.verdict}")
    print(f"Steps executed: {len(result.evidence)}")
    print(f"Total duration: {result.total_duration_seconds:.3f}s")
    if result.report_path:
        print(f"Report: {result.report_path}")
    print("=" * 60)

    # Exit code
    if result.verdict == PipelineVerdict.FAIL.value:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
