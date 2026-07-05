"""
Dataset assembly for AlphaForge — combines features + labels into
walk-forward training folds.

Manages:
- Feature-label alignment by symbol + timestamp
- Walk-forward fold generation with train/validation splits
- Exclusion rules (INVALID, AMBIGUOUS, insufficient data)
- Per-mode dataset construction
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from alphaforge.errors import AlphaForgeError

from lib.time.folds import generate_folds as _generate_folds


DEFAULT_FOLD_CONFIG = {
    "train_window_days": 365,
    "val_window_days": 60,
    "min_train_days": 365,
}

EXCLUSION_LABEL_VALIDITIES = {"AMBIGUOUS", "INVALID"}
EXCLUSION_RESOLUTION_STATUSES = {"UNRESOLVED", "INVALIDATED"}


def _to_timestamp(dt_str: str) -> str:
    return dt_str.replace("Z", "+00:00").replace(" ", "T")


def _to_date_int(dt_str: str) -> int:
    """Convert an ISO timestamp to Unix ms for generate_folds."""
    cleaned = dt_str.replace("Z", "+00:00").replace(" ", "T")
    try:
        dt = datetime.fromisoformat(cleaned)
        return int(dt.timestamp() * 1000)  # ms since epoch
    except (ValueError, TypeError):
        return 0


def _parse_date_str(dt_str: str) -> str:
    """Extract YYYY-MM-DD from an ISO timestamp."""
    cleaned = dt_str.replace("Z", "+00:00").replace(" ", "T")
    return cleaned.split("T")[0]


def align_features_and_labels(
    features: list[dict[str, Any]],
    labels: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Align feature rows with label rows by symbol + timestamp.

    Returns merged rows containing both features and label targets.
    Raises on duplicate (symbol, timestamp) pairs.

    Args:
        features: List of feature row dicts (must have 'symbol', 'timestamp', 'features').
        labels: List of AlphaForgeLabel dicts (must have 'symbol', 'timestamp').

    Returns:
        List of merged training rows sorted by timestamp then symbol.
    """
    label_map: dict[tuple[str, str], dict[str, Any]] = {}
    for label in labels:
        key = (label["symbol"], _to_timestamp(label["timestamp"]))
        if key in label_map:
            raise AlphaForgeError(f"Duplicate label for ({key[0]}, {key[1]})")
        label_map[key] = label

    merged: list[dict[str, Any]] = []
    for feat in features:
        key = (feat["symbol"], _to_timestamp(feat["timestamp"]))
        label = label_map.get(key)
        if label is None:
            continue
        merged.append({
            "symbol": feat["symbol"],
            "timestamp": feat["timestamp"],
            "mode": label.get("mode", ""),
            "features": copy.deepcopy(feat.get("features", {})),
            "label": copy.deepcopy(label),
        })

    merged.sort(key=lambda r: (_to_date_int(r["timestamp"]), r["symbol"]))
    return merged


def build_dataset(
    merged_rows: list[dict[str, Any]],
    mode: str,
    *,
    exclude_ambiguous: bool = True,
    exclude_invalid: bool = True,
    fold_config: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build a structured dataset with walk-forward folds.

    Args:
        merged_rows: Output from align_features_and_labels.
        mode: Mode name for the dataset.
        exclude_ambiguous: If True, exclude AMBIGUOUS labels.
        exclude_invalid: If True, exclude INVALID labels.
        fold_config: Overrides for DEFAULT_FOLD_CONFIG.

    Returns:
        Dataset dict with 'mode', 'total_rows', 'excluded', 'folds', etc.
    """
    config = dict(DEFAULT_FOLD_CONFIG)
    if fold_config:
        config.update(fold_config)

    excluded: dict[str, list[dict[str, Any]]] = {
        "ambiguous": [],
        "invalid": [],
    }
    training_rows: list[dict[str, Any]] = []

    for row in merged_rows:
        validity = row["label"].get("label_validity", "VALID")

        if exclude_invalid and validity == "INVALID":
            excluded["invalid"].append(row)
            continue
        if exclude_ambiguous and validity == "AMBIGUOUS":
            excluded["ambiguous"].append(row)
            continue
        training_rows.append(row)

    if len(training_rows) < 2:
        return {
            "mode": mode,
            "total_rows": len(training_rows),
            "excluded_counts": {k: len(v) for k, v in excluded.items()},
            "folds": [],
            "status": "insufficient_data",
        }

    # Build date range for fold generation
    date_ints = [_to_date_int(r["timestamp"]) for r in training_rows]
    dataset_start = min(date_ints)
    dataset_end = max(date_ints)

    folds = _generate_folds(
        dataset_start=dataset_start,
        dataset_end=dataset_end,
        train_window_days=config["train_window_days"],
        val_window_days=config["val_window_days"],
        min_train_days=config["min_train_days"],
    )

    # Assign rows to folds
    fold_assignments = []
    for fold in folds:
        train_start_int = fold.train_start
        train_end_int = fold.train_end
        val_start_int = fold.val_start
        val_end_int = fold.val_end

        train_rows = []
        val_rows = []
        for row in training_rows:
            rd = _to_date_int(row["timestamp"])
            if train_start_int <= rd <= train_end_int:
                train_rows.append(row)
            elif val_start_int <= rd <= val_end_int:
                val_rows.append(row)

        if not train_rows and not val_rows:
            continue

        fold_assignments.append({
            "fold_id": f"{mode.lower()}_fold_{fold.fold_id}",
            "train_start": str(fold.train_start),
            "train_end": str(fold.train_end),
            "val_start": str(fold.val_start),
            "val_end": str(fold.val_end),
            "num_train": len(train_rows),
            "num_val": len(val_rows),
        })

    return {
        "mode": mode,
        "total_rows": len(training_rows),
        "excluded_counts": {k: len(v) for k, v in excluded.items()},
        "folds": fold_assignments,
        "status": "ready" if fold_assignments else "insufficient_data",
        "fold_config": config,
    }


def get_feature_keys(merged_rows: list[dict[str, Any]]) -> list[str]:
    """Extract sorted feature column names from merged rows."""
    keys: set[str] = set()
    for row in merged_rows:
        keys.update(row.get("features", {}).keys())
    return sorted(keys)
