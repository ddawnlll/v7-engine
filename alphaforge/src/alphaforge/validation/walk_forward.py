"""WalkForwardValidator — chronological fold split and ValidationReport assembly.

Implements the WalkForwardValidator class that splits a datetime-sorted
LabeledDataset into chronological walk-forward folds, validates chronological
ordering, enforces 6-fold minimum, verifies purge/embargo constraints, and
assembles a ValidationReport with all metrics set to NOT_EVALUATED.

This module imports ZERO ML libraries (no xgboost, sklearn, tensorflow, torch).
The only real numbers in any report are structural: fold counts and sample counts.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple

from alphaforge.validation.contracts import (
    NOT_EVALUATED,
    MODE_PURGE_BARS,
    CostStressResult,
    Fold,
    FoldResult,
    MHTControls,
    Mode,
    OOSSummary,
    OverfitFlag,
    PurgePolicy,
    RegimeBreakdown,
    SymbolStability,
    ValidationError,
    ValidationReport,
    ValidationVerdict,
    WalkForwardConfig,
    WindowType,
    _distinct_bars_between,
    _get_timestamps,
    _distinct_timestamp_count,
)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_chronological_order(
    dataset: List[Any],
) -> List[str]:
    """Verify dataset is sorted by (feature_timestamp, symbol).

    Returns sorted list of distinct timestamps for downstream use.
    Raises ValidationError if any element is out of order.
    """
    if not dataset:
        raise ValidationError(
            message="Cannot validate empty dataset.",
            suggestion="Provide a non-empty dataset with at least 6 folds' worth of data.",
        )

    prev_ts = ""
    prev_sym = ""
    timestamps: List[str] = []

    for i, row in enumerate(dataset):
        ts = row.feature_timestamp
        sym = row.symbol

        # Check chronological ordering
        if prev_ts and (ts < prev_ts or (ts == prev_ts and sym < prev_sym)):
            raise ValidationError(
                message=(
                    f"Dataset is not chronologically sorted at row {i}: "
                    f"({prev_ts}, {prev_sym}) then ({ts}, {sym}). "
                    f"Dataset must be sorted by (feature_timestamp, symbol) ascending."
                ),
                suggestion="Sort the dataset before calling split().",
            )

        prev_ts = ts
        prev_sym = sym

        if not timestamps or timestamps[-1] != ts:
            timestamps.append(ts)

    return timestamps


def _compute_bar_positions(
    config: WalkForwardConfig,
    total_bars: int,
    fold_index: int,
) -> Tuple[int, int, int, int]:
    """Compute bar positions for one fold's train and test windows.

    Returns (train_start_bar, train_end_bar, test_start_bar, test_end_bar)
    as positions in bar space (0-indexed into distinct timestamps).

    For ANCHORED: train_start is always 0, train_end expands.
    For ROLLING: train_start advances by (test_window + purge) each fold.
    """
    tw = config.train_window_bars
    tsw = config.test_window_bars
    p = config.purge_bars

    if config.window_type == WindowType.ANCHORED:
        train_start_bar = 0
        train_end_bar = tw + fold_index * (tsw + p)
    else:  # ROLLING
        train_start_bar = fold_index * (tsw + p)
        train_end_bar = train_start_bar + tw

    test_start_bar = train_end_bar + p
    test_end_bar = test_start_bar + tsw

    return train_start_bar, train_end_bar, test_start_bar, test_end_bar


def _compute_max_folds(config: WalkForwardConfig, total_bars: int) -> int:
    """Compute maximum possible folds for the given config and bar count."""
    tw = config.train_window_bars
    tsw = config.test_window_bars
    p = config.purge_bars

    if tw + tsw > total_bars:
        return 0

    return (total_bars - tw - tsw) // (tsw + p) + 1


def _bar_to_dataset_indices(
    dataset: List[Any],
    bar_map: Dict[str, Tuple[int, int]],
    timestamps: List[str],
    bar_start: int,
    bar_end: int,
) -> List[int]:
    """Convert bar range [bar_start, bar_end) to dataset row indices."""
    indices: List[int] = []
    for bar_idx in range(bar_start, min(bar_end, len(timestamps))):
        ts = timestamps[bar_idx]
        start, end = bar_map.get(ts, (0, 0))
        indices.extend(range(start, min(end, len(dataset))))
    return indices


# ---------------------------------------------------------------------------
# WalkForwardValidator
# ---------------------------------------------------------------------------

class WalkForwardValidator:
    """Chronological walk-forward fold splitter and report assembler.

    Takes a WalkForwardConfig and PurgePolicy.  Splits a LabeledDataset into
    chronological folds respecting purge/embargo constraints.  Assembles a
    ValidationReport where ALL metrics are NOT_EVALUATED.

    Constructor:
        config: WalkForwardConfig with mode, window sizes, split ratios.
        purge_policy: PurgePolicy with mode-specific purge/embargo bars.
    """

    def __init__(
        self, config: WalkForwardConfig, purge_policy: PurgePolicy
    ) -> None:
        self._config = config
        self._purge_policy = purge_policy

    @property
    def config(self) -> WalkForwardConfig:
        return self._config

    @property
    def purge_policy(self) -> PurgePolicy:
        return self._purge_policy

    # ------------------------------------------------------------------
    # split()
    # ------------------------------------------------------------------

    def split(self, dataset: List[Any]) -> List[Fold]:
        """Split a datetime-sorted dataset into chronological folds.

        Args:
            dataset: List of LabeledDataset rows, sorted by
                     (feature_timestamp, symbol) ascending.

        Returns:
            List[Fold] with >= min_folds entries, each containing
            train/val/oos indices and datetime boundaries.

        Raises:
            ValidationError: If dataset is unsorted, too small, or violates
                             purge/embargo constraints.
        """
        config = self._config
        policy = self._purge_policy

        # 1. Validate chronological ordering; collect distinct timestamps
        timestamps = _validate_chronological_order(dataset)
        total_bars = len(timestamps)

        # 2. Build bar->index map for fast lookup
        bar_map: Dict[str, Tuple[int, int]] = {}
        for i, row in enumerate(dataset):
            ts = row.feature_timestamp
            if ts not in bar_map:
                bar_map[ts] = (i, i + 1)
            else:
                start, _ = bar_map[ts]
                bar_map[ts] = (start, i + 1)

        # 3. Compute maximum possible folds
        max_folds = _compute_max_folds(config, total_bars)

        if max_folds < config.min_folds:
            # Compute minimum bars needed
            tw = config.train_window_bars
            tsw = config.test_window_bars
            p = config.purge_bars
            required_bars = tw + tsw + (config.min_folds - 1) * (tsw + p)

            raise ValidationError(
                message=(
                    f"Dataset of {total_bars} bars cannot satisfy "
                    f"{config.min_folds}-fold minimum for mode {config.mode.value}. "
                    f"Maximum possible folds: {max_folds}. "
                    f"Minimum bars needed: {required_bars}."
                ),
                mode=config.mode,
                required_folds=config.min_folds,
                available_bars=total_bars,
                required_bars=required_bars,
                suggestion=(
                    f"Add more data or reduce fold count. "
                    f"Shortest mode: SWING (2000/500 bars). "
                    f"Available: {total_bars} bars. Required: {required_bars} bars."
                ),
            )

        # 4. Build folds
        folds: List[Fold] = []
        val_ratio = config.val_ratio
        oos_ratio = config.oos_ratio
        test_alloc = val_ratio + oos_ratio

        for fold_idx in range(max_folds):
            train_sb, train_eb, test_sb, test_eb = _compute_bar_positions(
                config, total_bars, fold_idx
            )

            # Clamp to valid ranges
            train_eb = min(train_eb, total_bars)
            test_eb = min(test_eb, total_bars)

            if test_sb >= total_bars or test_sb >= test_eb:
                break

            # Split test window into val and oos
            test_bar_count = test_eb - test_sb
            purge = config.purge_bars
            available_for_val_oos = max(1, test_bar_count - purge)

            val_bars = max(1, int(available_for_val_oos * val_ratio / test_alloc))
            oos_bars = max(1, available_for_val_oos - val_bars)

            val_start_bar = test_sb
            val_end_bar = min(test_sb + val_bars, test_eb)
            oos_start_bar = min(val_end_bar + purge, total_bars)
            oos_end_bar = min(oos_start_bar + oos_bars, test_eb)

            # Get actual dataset indices
            train_indices = _bar_to_dataset_indices(
                dataset, bar_map, timestamps, train_sb, train_eb
            )
            val_indices = _bar_to_dataset_indices(
                dataset, bar_map, timestamps, val_start_bar, val_end_bar
            )
            oos_indices = _bar_to_dataset_indices(
                dataset, bar_map, timestamps, oos_start_bar, oos_end_bar
            )

            if not train_indices or not val_indices or not oos_indices:
                break

            # Datetime boundaries from first/last row in each set
            train_start = dataset[train_indices[0]].feature_timestamp
            train_end = dataset[train_indices[-1]].feature_timestamp
            val_start = dataset[val_indices[0]].feature_timestamp
            val_end = dataset[val_indices[-1]].feature_timestamp
            oos_start = dataset[oos_indices[0]].feature_timestamp
            oos_end = dataset[oos_indices[-1]].feature_timestamp

            # Purge gaps (in bars)
            purge_before_val = _distinct_bars_between(
                dataset,
                _get_timestamps(dataset, train_indices),
                _get_timestamps(dataset, val_indices),
            )
            purge_before_oos = _distinct_bars_between(
                dataset,
                _get_timestamps(dataset, val_indices),
                _get_timestamps(dataset, oos_indices),
            )

            # Embargo check
            embargo_applied = False
            min_embargo = _min_bar_dist(
                dataset, train_indices, val_indices + oos_indices
            )
            if min_embargo >= config.embargo_bars:
                embargo_applied = True

            fold = Fold(
                fold_index=fold_idx,
                train_start=train_start,
                train_end=train_end,
                val_start=val_start,
                val_end=val_end,
                oos_start=oos_start,
                oos_end=oos_end,
                train_indices=train_indices,
                val_indices=val_indices,
                oos_indices=oos_indices,
                purge_before_val=purge_before_val,
                purge_before_oos=purge_before_oos,
                embargo_applied=embargo_applied,
            )

            # Validate purge gaps
            policy.validate_purge(fold, dataset)

            folds.append(fold)

        # 5. Enforce 6-fold minimum on actual folds produced
        if len(folds) < config.min_folds:
            raise ValidationError(
                message=(
                    f"Only {len(folds)} folds could be constructed from "
                    f"{total_bars} bars, but mode {config.mode.value} requires "
                    f">= {config.min_folds} folds."
                ),
                mode=config.mode,
                required_folds=config.min_folds,
                available_bars=total_bars,
                suggestion=(
                    f"Add more data. Available: {total_bars} bars, "
                    f"folds produced: {len(folds)}, minimum: {config.min_folds}."
                ),
            )

        return folds

    # ------------------------------------------------------------------
    # assemble_validation_report()
    # ------------------------------------------------------------------

    def assemble_validation_report(
        self, dataset: List[Any]
    ) -> ValidationReport:
        """Split dataset and assemble a ValidationReport skeleton.

        All metric fields use NOT_EVALUATED.  Only sample_counts per fold
        contain real (structural) integers.

        Returns:
            ValidationReport with verdict INCONCLUSIVE and all metrics
            NOT_EVALUATED.
        """
        config = self._config
        folds = self.split(dataset)

        # Build FoldResults
        fold_results: List[FoldResult] = []
        for fold in folds:
            sample_counts = {
                "train": len(fold.train_indices),
                "val": len(fold.val_indices),
                "oos": len(fold.oos_indices),
            }
            fr = FoldResult(
                fold_index=fold.fold_index,
                train_metrics=NOT_EVALUATED,
                val_metrics=NOT_EVALUATED,
                oos_metrics=NOT_EVALUATED,
                regime_breakdown=NOT_EVALUATED,
                cost_stress=NOT_EVALUATED,
                sample_counts=sample_counts,
            )
            fold_results.append(fr)

        # Report ID
        report_id = _make_report_id(config, len(dataset))
        generated_at = datetime.now(timezone.utc).isoformat()

        report = ValidationReport(
            config=config,
            folds=fold_results,
            oos_summary=OOSSummary(),
            cost_stress=CostStressResult(),
            regime_breakdown=RegimeBreakdown(),
            symbol_stability=SymbolStability(),
            overfit_risk_flags=[],
            mht_controls=MHTControls(),
            verdict=ValidationVerdict.INCONCLUSIVE,
            report_id=report_id,
            generated_at=generated_at,
        )

        return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _min_bar_dist(
    dataset: List[Any],
    train_indices: List[int],
    test_indices: List[int],
) -> int:
    """Compute minimum bar distance between train and test index sets."""
    train_ts = _get_timestamps(dataset, train_indices)
    test_ts = _get_timestamps(dataset, test_indices)

    if not train_ts or not test_ts:
        return 0

    # If they share any timestamp, distance is 0
    if train_ts & test_ts:
        return 0

    max_train = max(train_ts)
    min_test = min(test_ts)

    if max_train < min_test:
        return _distinct_bars_between(dataset, {max_train}, {min_test})

    # Test before train — shouldn't happen
    max_test = max(test_ts)
    min_train = min(train_ts)
    if max_test < min_train:
        return _distinct_bars_between(dataset, {max_test}, {min_train})

    return 0


def _make_report_id(config: WalkForwardConfig, dataset_len: int) -> str:
    """Generate deterministic report ID: VR-{mode}-{timestamp}-{hash_8chars}."""
    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y-%m-%dT%H:%M:%S")
    raw = f"{config.mode.value}|{config.train_window_bars}|{config.test_window_bars}|{dataset_len}|{now.isoformat()}"
    hash_part = hashlib.sha256(raw.encode()).hexdigest()[:8]
    return f"VR-{config.mode.value}-{date_part}-{hash_part}"
