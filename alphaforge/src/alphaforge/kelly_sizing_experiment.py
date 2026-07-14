"""Research-only Kelly sizing experiment for the V7-Lite 56-symbol panel.

This module deliberately keeps the XGBoost training code inside AlphaForge's
source tree when installed remotely.  It produces a reproducible JSON artifact
only; it neither writes a model artifact nor authorizes runtime execution.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PANEL_DIR = Path("/root/v7-engine/cache/v7_lite_expanded_panel_v1")
DEFAULT_OUTPUT = REPO_ROOT / "data/reports/kelly_sizing_results.json"
FIELDS = ("open", "high", "low", "close", "volume")
THRESHOLDS = tuple(round(float(value), 2) for value in np.arange(0.30, 0.901, 0.05))


@dataclass(frozen=True)
class FoldSpec:
    """One timestamp-grouped expanding-window split."""

    fold: int
    train_rows: int
    validation_rows: int
    train_groups: int
    validation_groups: int
    nominal_boundary_group: int
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str


def _timestamp_divisor(timestamps: np.ndarray) -> int:
    """Return the timestamp unit denominator for epoch-day calculations."""

    maximum = int(np.max(np.abs(timestamps))) if len(timestamps) else 0
    if maximum >= 10**17:
        return 86_400_000_000_000  # nanoseconds per day
    if maximum >= 10**14:
        return 86_400_000_000  # microseconds per day
    if maximum >= 10**11:
        return 86_400_000  # milliseconds per day
    return 86_400  # seconds per day


def _to_iso_utc(timestamp: int) -> str:
    """Render an epoch timestamp in seconds/ms/us/ns as an ISO-8601 UTC value."""

    value = int(timestamp)
    absolute = abs(value)
    if absolute >= 10**17:
        seconds = value / 1_000_000_000
    elif absolute >= 10**14:
        seconds = value / 1_000_000
    elif absolute >= 10**11:
        seconds = value / 1_000
    else:
        seconds = value
    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _json_default(value: Any) -> Any:
    """Convert NumPy values without silently serializing non-finite numbers."""

    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Not JSON serializable: {type(value)!r}")


def load_panel(panel_dir: Path) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Load and validate the five long-format OHLCV panel files.

    All field files must have identical timestamp/symbol row identity.  The
    check prevents accidentally combining values from mismatched panel builds.
    """

    anchor_path = panel_dir / "panel_v7lite_expanded_close.parquet"
    if not anchor_path.is_file():
        raise FileNotFoundError(f"Missing close panel: {anchor_path}")

    anchor = pd.read_parquet(anchor_path, columns=["timestamp", "symbol", "close"])
    timestamps = anchor["timestamp"].to_numpy(dtype=np.int64, copy=True)
    symbols = anchor["symbol"].astype(str).to_numpy(copy=True)
    ohlcv: dict[str, np.ndarray] = {
        "timestamp": timestamps,
        "symbol": symbols,
        "close": anchor["close"].to_numpy(dtype=np.float64, copy=True),
    }
    del anchor

    for field in FIELDS:
        if field == "close":
            continue
        path = panel_dir / f"panel_v7lite_expanded_{field}.parquet"
        if not path.is_file():
            raise FileNotFoundError(f"Missing {field} panel: {path}")
        frame = pd.read_parquet(path, columns=["timestamp", "symbol", field])
        field_timestamps = frame["timestamp"].to_numpy(dtype=np.int64, copy=False)
        field_symbols = frame["symbol"].astype(str).to_numpy(copy=False)
        if not np.array_equal(field_timestamps, timestamps) or not np.array_equal(field_symbols, symbols):
            raise ValueError(f"{field} panel row identity differs from close panel")
        ohlcv[field] = frame[field].to_numpy(dtype=np.float64, copy=True)
        del frame

    if np.any(timestamps[1:] < timestamps[:-1]):
        raise ValueError("Panel is not timestamp ordered")
    unique_symbols = sorted(set(symbols.tolist()))
    if len(unique_symbols) != 56:
        raise ValueError(f"Expected 56 symbols, found {len(unique_symbols)}")

    metadata = {
        "panel_dir": str(panel_dir),
        "raw_rows": int(len(timestamps)),
        "symbols_count": len(unique_symbols),
        "symbols": unique_symbols,
        "timestamp_start": _to_iso_utc(int(timestamps.min())),
        "timestamp_end": _to_iso_utc(int(timestamps.max())),
    }
    return ohlcv, metadata


def build_splits(
    timestamps: np.ndarray,
    *,
    n_folds: int,
    label_horizon: int,
) -> tuple[list[tuple[FoldSpec, slice, slice]], dict[str, int]]:
    """Make exactly ``n_folds`` purged expanding splits at timestamp boundaries.

    The gap is intentionally measured in timestamp groups rather than flattened
    rows.  This keeps all symbols at a given candle timestamp on the same side
    of every split.  The conservative gap sizing matches the existing AlphaForge
    WFV policy: purge=max(block/4, 2*horizon), embargo=max(block/8, 2*horizon).
    """

    group_times = np.unique(timestamps)
    block_groups = len(group_times) // (n_folds + 1)
    if block_groups <= 0:
        raise ValueError("Insufficient timestamp groups for walk-forward validation")
    purge_groups = max(block_groups // 4, 2 * label_horizon)
    embargo_groups = max(block_groups // 8, 2 * label_horizon)
    if block_groups <= purge_groups + embargo_groups + 20:
        raise ValueError(
            "Timestamp block is too small after purge/embargo: "
            f"block={block_groups}, purge={purge_groups}, embargo={embargo_groups}"
        )

    splits: list[tuple[FoldSpec, slice, slice]] = []
    for zero_based_fold in range(n_folds):
        boundary = (zero_based_fold + 1) * block_groups
        train_group_end = boundary - purge_groups
        validation_group_start = boundary + embargo_groups
        validation_group_end = min((zero_based_fold + 2) * block_groups, len(group_times))
        if train_group_end <= 0 or validation_group_start >= validation_group_end:
            raise ValueError(f"Fold {zero_based_fold + 1} has invalid purge/embargo boundaries")

        train_row_end = int(np.searchsorted(timestamps, group_times[train_group_end], side="left"))
        validation_row_start = int(
            np.searchsorted(timestamps, group_times[validation_group_start], side="left")
        )
        validation_row_end = (
            len(timestamps)
            if validation_group_end == len(group_times)
            else int(np.searchsorted(timestamps, group_times[validation_group_end], side="left"))
        )
        if train_row_end <= 0 or validation_row_end <= validation_row_start:
            raise ValueError(f"Fold {zero_based_fold + 1} has no train or validation rows")

        spec = FoldSpec(
            fold=zero_based_fold + 1,
            train_rows=train_row_end,
            validation_rows=validation_row_end - validation_row_start,
            train_groups=train_group_end,
            validation_groups=validation_group_end - validation_group_start,
            nominal_boundary_group=boundary,
            train_start=_to_iso_utc(int(group_times[0])),
            train_end=_to_iso_utc(int(group_times[train_group_end - 1])),
            validation_start=_to_iso_utc(int(group_times[validation_group_start])),
            validation_end=_to_iso_utc(int(group_times[validation_group_end - 1])),
        )
        splits.append((spec, slice(0, train_row_end), slice(validation_row_start, validation_row_end)))

    split_config = {
        "n_timestamp_groups": int(len(group_times)),
        "block_groups": int(block_groups),
        "label_horizon_bars": int(label_horizon),
        "purge_groups": int(purge_groups),
        "embargo_groups": int(embargo_groups),
    }
    return splits, split_config


def choose_device() -> str:
    """Use CUDA only when the installed XGBoost build and device support it."""

    try:
        has_cuda = bool(xgb.build_info().get("USE_CUDA"))
    except Exception:
        has_cuda = False
    return "cuda" if has_cuda and shutil.which("nvidia-smi") else "cpu"


def classifier_params(device: str) -> dict[str, Any]:
    """Return the fixed single-model baseline used in every fold."""

    params: dict[str, Any] = {
        "n_estimators": 120,
        "max_depth": 4,
        "learning_rate": 0.05,
        "objective": "multi:softprob",
        "num_class": 3,
        "random_state": 42,
        "verbosity": 0,
        "subsample": 0.8,
        "colsample_bytree": 1.0,
        "eval_metric": "mlogloss",
        "tree_method": "hist",
        "device": device,
    }
    if device == "cpu":
        params["n_jobs"] = min(os.cpu_count() or 1, 16)
    return params


def kelly_stats(trade_returns: np.ndarray) -> dict[str, Any]:
    """Compute economic win/loss statistics and both requested Kelly schemes."""

    trade_count = int(len(trade_returns))
    if trade_count == 0:
        return {
            "trade_count": 0,
            "winrate": None,
            "avg_win": None,
            "avg_loss": None,
            "base_net_R": None,
            "payoff_ratio_b": None,
            "raw_kelly_fraction": None,
            "standard_half_kelly": {"kelly_fraction": None, "leverage": 0.0, "adjusted_R": None},
            "conservative_quarter_kelly": {"kelly_fraction": None, "leverage": 0.0, "adjusted_R": None},
        }

    wins = trade_returns[trade_returns > 0.0]
    losses = trade_returns[trade_returns <= 0.0]
    winrate = float(len(wins) / trade_count)
    base_net_r = float(np.mean(trade_returns))
    avg_win = float(np.mean(wins)) if len(wins) else 0.0
    avg_loss = float(abs(np.mean(losses))) if len(losses) else 0.0

    if not len(wins):
        payoff_ratio = 0.0
        raw_kelly = 0.0
        kelly_note = "No positive economic outcomes; Kelly is set to zero."
    elif not len(losses) or avg_loss <= 0.0:
        payoff_ratio = None
        raw_kelly = 1.0
        kelly_note = "No observed losses; raw Kelly uses the p→1 limiting value and is cap-limited."
    else:
        payoff_ratio = avg_win / avg_loss
        raw_kelly = (winrate * payoff_ratio - (1.0 - winrate)) / payoff_ratio
        kelly_note = None

    raw_kelly_clipped = max(0.0, float(raw_kelly))

    def scheme(name: str, multiplier: float, leverage_cap: float) -> dict[str, Any]:
        fraction = raw_kelly_clipped * multiplier
        leverage = min(fraction * 5.0, leverage_cap)
        return {
            "name": name,
            "kelly_fraction": float(fraction),
            "leverage": float(leverage),
            "adjusted_R": float(base_net_r * leverage),
            "leverage_formula": f"min(({multiplier:g} * raw_kelly_fraction) * 5, {leverage_cap:g})",
        }

    return {
        "trade_count": trade_count,
        "winrate": winrate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "base_net_R": base_net_r,
        "payoff_ratio_b": payoff_ratio,
        "raw_kelly_fraction": float(raw_kelly),
        "raw_kelly_fraction_clipped": raw_kelly_clipped,
        "kelly_note": kelly_note,
        "standard_half_kelly": scheme("standard_half_kelly", 0.5, 5.0),
        "conservative_quarter_kelly": scheme("conservative_quarter_kelly", 0.25, 3.0),
    }


def evaluate_thresholds(
    predictions: np.ndarray,
    confidence: np.ndarray,
    y_true: np.ndarray,
    action_net_r: np.ndarray,
    timestamps: np.ndarray,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Score every requested confidence threshold using concatenated OOS rows."""

    results: list[dict[str, Any]] = []
    day_divisor = _timestamp_divisor(timestamps)
    for threshold in THRESHOLDS:
        active = (predictions != 2) & (confidence >= threshold)
        active_indices = np.flatnonzero(active)
        trade_returns = (
            action_net_r[active_indices, predictions[active_indices]]
            if len(active_indices)
            else np.empty(0, dtype=np.float64)
        )
        stats = kelly_stats(trade_returns)
        active_days = int(len(np.unique(timestamps[active_indices] // day_divisor))) if len(active_indices) else 0
        directional_accuracy = (
            float(np.mean(predictions[active_indices] == y_true[active_indices]))
            if len(active_indices)
            else None
        )
        result = {
            "threshold": threshold,
            "candidate_trades": int(len(active_indices)),
            "oos_calendar_days_with_candidates": active_days,
            "candidate_trades_per_day": float(len(active_indices) / active_days) if active_days else 0.0,
            "directional_accuracy": directional_accuracy,
            **stats,
        }
        results.append(result)

    candidates: list[dict[str, Any]] = []
    for row in results:
        if row["winrate"] is None or row["winrate"] < 0.80:
            continue
        for scheme_key in ("standard_half_kelly", "conservative_quarter_kelly"):
            scheme = row[scheme_key]
            candidates.append(
                {
                    "threshold": row["threshold"],
                    "scheme": scheme_key,
                    "leverage": scheme["leverage"],
                    "adjusted_R": scheme["adjusted_R"],
                    "base_net_R": row["base_net_R"],
                    "winrate": row["winrate"],
                    "candidate_trades": row["candidate_trades"],
                    "candidate_trades_per_day": row["candidate_trades_per_day"],
                }
            )

    best_80 = max(candidates, key=lambda item: (item["adjusted_R"], item["candidate_trades"])) if candidates else None
    one_plus_daily = [item for item in candidates if item["candidate_trades_per_day"] >= 1.0]
    best_80_one_plus_daily = (
        max(one_plus_daily, key=lambda item: (item["adjusted_R"], item["candidate_trades"]))
        if one_plus_daily
        else None
    )
    all_sized = [
        {
            "threshold": row["threshold"],
            "scheme": scheme_key,
            "leverage": row[scheme_key]["leverage"],
            "adjusted_R": row[scheme_key]["adjusted_R"],
            "winrate": row["winrate"],
            "candidate_trades": row["candidate_trades"],
        }
        for row in results
        if row["base_net_R"] is not None
        for scheme_key in ("standard_half_kelly", "conservative_quarter_kelly")
    ]
    best_any = max(all_sized, key=lambda item: (item["adjusted_R"], item["candidate_trades"])) if all_sized else None
    return results, {
        "target_winrate": 0.80,
        "best_80pct_winrate_by_adjusted_R": best_80,
        "best_80pct_winrate_and_one_plus_trade_per_day": best_80_one_plus_daily,
        "best_any_threshold_and_scheme_by_adjusted_R": best_any,
        "qualifying_80pct_candidates": candidates,
    }


def run_experiment(panel_dir: Path, output_path: Path, mode: str, n_folds: int) -> dict[str, Any]:
    """Train one fixed XGBoost model per purged expanding fold and write results."""

    from alphaforge.train import _get_training_config, build_aligned_training_frame

    started_at = datetime.now(timezone.utc)
    ohlcv, panel_metadata = load_panel(panel_dir)
    training_frame = build_aligned_training_frame(ohlcv, mode)
    config = _get_training_config(mode)

    raw_X = np.asarray(training_frame["X"], dtype=np.float32)
    feature_names = list(training_frame["feature_names"])
    nonfinite_feature_values = int(np.count_nonzero(~np.isfinite(raw_X)))
    X = np.nan_to_num(raw_X, nan=0.0, posinf=0.0, neginf=0.0, copy=True)
    y_int = np.asarray(training_frame["y_int"], dtype=np.int32)
    action_net_r = np.asarray(training_frame["action_net_r"], dtype=np.float64)
    timestamps = np.asarray(training_frame["timestamps"], dtype=np.int64)
    symbols = np.asarray(training_frame["symbols"], dtype=str)
    del raw_X, training_frame, ohlcv
    gc.collect()

    if len(X) == 0 or len(X) != len(y_int) or len(X) != len(action_net_r) or len(X) != len(timestamps):
        raise ValueError("Training-frame arrays are empty or misaligned")
    if action_net_r.shape != (len(X), 3):
        raise ValueError(f"Expected action_net_r shape {(len(X), 3)}, got {action_net_r.shape}")
    if np.any(timestamps[1:] < timestamps[:-1]):
        raise ValueError("Aligned training frame is not timestamp ordered")

    splits, split_config = build_splits(
        timestamps,
        n_folds=n_folds,
        label_horizon=int(config.label_horizon),
    )
    selected_device = choose_device()
    runtime_device = selected_device
    actual_devices: list[str] = []
    fold_specs: list[dict[str, Any]] = []
    oos_predictions: list[np.ndarray] = []
    oos_confidence: list[np.ndarray] = []
    oos_y_true: list[np.ndarray] = []
    oos_action_net_r: list[np.ndarray] = []
    oos_timestamps: list[np.ndarray] = []
    oos_symbols: list[np.ndarray] = []

    for spec, train_slice, validation_slice in splits:
        X_train = X[train_slice]
        y_train = y_int[train_slice]
        X_validation = X[validation_slice]
        y_validation = y_int[validation_slice]
        if len(np.unique(y_train)) < 2:
            raise ValueError(f"Fold {spec.fold} train data has fewer than two classes")

        params = classifier_params(runtime_device)
        classifier = xgb.XGBClassifier(**params)
        try:
            classifier.fit(X_train, y_train)
        except xgb.core.XGBoostError:
            if runtime_device != "cuda":
                raise
            runtime_device = "cpu"
            params = classifier_params(runtime_device)
            classifier = xgb.XGBClassifier(**params)
            classifier.fit(X_train, y_train)
        actual_devices.append(runtime_device)

        probabilities = classifier.predict_proba(X_validation)
        predictions = np.argmax(probabilities, axis=1).astype(np.int8, copy=False)
        confidence = np.max(probabilities, axis=1).astype(np.float64, copy=False)
        fold_accuracy = float(np.mean(predictions == y_validation))
        fold_record = asdict(spec)
        fold_record.update(
            {
                "device": runtime_device,
                "model_accuracy": fold_accuracy,
                "train_class_counts": {
                    str(label): int(np.count_nonzero(y_train == label)) for label in range(3)
                },
                "validation_class_counts": {
                    str(label): int(np.count_nonzero(y_validation == label)) for label in range(3)
                },
            }
        )
        fold_specs.append(fold_record)
        oos_predictions.append(predictions)
        oos_confidence.append(confidence)
        oos_y_true.append(y_validation)
        oos_action_net_r.append(action_net_r[validation_slice])
        oos_timestamps.append(timestamps[validation_slice])
        oos_symbols.append(symbols[validation_slice])
        del classifier, probabilities
        gc.collect()

    predictions = np.concatenate(oos_predictions)
    confidence = np.concatenate(oos_confidence)
    y_true = np.concatenate(oos_y_true)
    oos_action = np.concatenate(oos_action_net_r)
    oos_timestamps_array = np.concatenate(oos_timestamps)
    oos_symbols_array = np.concatenate(oos_symbols)
    threshold_results, selection = evaluate_thresholds(
        predictions, confidence, y_true, oos_action, oos_timestamps_array
    )

    now = datetime.now(timezone.utc)
    output = {
        "experiment": "kelly_sizing_purged_walk_forward",
        "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "result_status": "RESEARCH_ONLY_NOT_EXECUTION_AUTHORIZATION",
        "scope": "56-symbol 1h panel; fixed XGBoost multi-class model; six expanding purged/embargoed OOS folds",
        "data": panel_metadata,
        "feature_frame": {
            "rows": int(len(X)),
            "features": int(X.shape[1]),
            "expected_features": 91,
            "matches_expected_feature_count": bool(X.shape[1] == 91),
            "feature_names": feature_names,
            "nonfinite_feature_values_replaced_with_zero": nonfinite_feature_values,
            "label_unit": "fractional net forward return from alphaforge.train.action_net_r; not risk-normalized economic R",
        },
        "model": {
            "selected_device": selected_device,
            "actual_fold_devices": actual_devices,
            "parameters": classifier_params(actual_devices[-1] if actual_devices else selected_device),
        },
        "walk_forward": {
            "method": "timestamp_grouped_expanding_purged_embargoed",
            **split_config,
            "folds": fold_specs,
            "oos_rows": int(len(predictions)),
            "oos_timestamp_start": _to_iso_utc(int(oos_timestamps_array.min())),
            "oos_timestamp_end": _to_iso_utc(int(oos_timestamps_array.max())),
            "oos_symbols_count": int(len(set(oos_symbols_array.tolist()))),
        },
        "formulae": {
            "raw_kelly": "(p * b - q) / b, where p=economic win probability, q=1-p, b=avg_win/avg_loss",
            "standard_half_kelly": "kelly_fraction=max(raw_kelly, 0)*0.5; leverage=min(kelly_fraction*5, 5)",
            "conservative_quarter_kelly": "kelly_fraction=max(raw_kelly, 0)*0.25; leverage=min(kelly_fraction*5, 3)",
            "adjusted_R": "base_net_R * leverage",
            "win_definition": "predicted action's action_net_r is strictly positive",
        },
        "threshold_results": threshold_results,
        "selection": selection,
        "limitations": [
            "This is a retrospective threshold sweep across OOS folds; the selected threshold still needs an untouched post-selection holdout.",
            "Candidate trades are model action opportunities, not overlap-filtered executable fills.",
            "Leverage is a mathematical sizing illustration only; it excludes leverage-dependent liquidation, quantity rounding, and exchange-margin parity.",
            "No result authorizes live, paper, or shadow execution.",
        ],
        "elapsed_seconds": round((now - started_at).total_seconds(), 3),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, allow_nan=False, default=_json_default) + "\n")

    print("KELLY SIZING — RESEARCH ONLY")
    print("threshold  trades  winrate  base_net_R  half_lev  half_adj_R  qtr_lev  qtr_adj_R")
    for row in threshold_results:
        half_scheme = row["standard_half_kelly"]
        quarter_scheme = row["conservative_quarter_kelly"]
        if row["base_net_R"] is None:
            print(f"{row['threshold']:>8.2f} {0:>7d}       n/a         n/a      0.000        n/a    0.000       n/a")
        else:
            print(
                f"{row['threshold']:>8.2f} {row['candidate_trades']:>7d} "
                f"{row['winrate']:>7.2%} {row['base_net_R']:>11.6f} "
                f"{half_scheme['leverage']:>9.3f} {half_scheme['adjusted_R']:>11.6f} "
                f"{quarter_scheme['leverage']:>8.3f} {quarter_scheme['adjusted_R']:>11.6f}"
            )
    print(f"Wrote {output_path}")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-dir", type=Path, default=DEFAULT_PANEL_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--mode", default="SCALP", choices=("SCALP",))
    parser.add_argument("--folds", type=int, default=6)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.folds != 6:
        raise ValueError("This registered experiment is fixed to the requested six folds")
    run_experiment(args.panel_dir, args.output, args.mode, args.folds)


if __name__ == "__main__":
    main()
