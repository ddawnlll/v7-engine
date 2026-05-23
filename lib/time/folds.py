"""
Walk-forward fold generation.

Shared by both v7/ and alphaforge/ for temporal cross-validation.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Fold:
    """A single walk-forward fold."""
    fold_id: int
    train_start: int   # Unix ms
    train_end: int     # Unix ms (exclusive)
    val_start: int     # Unix ms
    val_end: int       # Unix ms (exclusive)


def generate_folds(
    dataset_start: int,
    dataset_end: int,
    train_window_days: int = 365,
    val_window_days: int = 60,
    min_train_days: Optional[int] = None,
) -> list[Fold]:
    """Generate walk-forward temporal folds.

    Args:
        dataset_start: Start of full dataset (Unix ms).
        dataset_end: End of full dataset (Unix ms).
        train_window_days: Training window length in days.
        val_window_days: Validation window length in days.
        min_train_days: Minimum training window required (default = train_window_days).

    Returns:
        List of Fold objects, ordered chronologically.

    Raises:
        ValueError: If dataset range is too short for even one fold.
    """
    if min_train_days is None:
        min_train_days = train_window_days

    ms_per_day = 86_400_000
    train_ms = train_window_days * ms_per_day
    val_ms = val_window_days * ms_per_day
    min_train_ms = min_train_days * ms_per_day
    step_ms = val_ms  # advance by validation window length

    folds: list[Fold] = []
    fold_id = 0
    current_train_end = dataset_start + train_ms

    while current_train_end + val_ms <= dataset_end:
        train_start_ms = current_train_end - train_ms
        if train_start_ms < dataset_start:
            train_start_ms = dataset_start

        train_duration = current_train_end - train_start_ms
        if train_duration >= min_train_ms:
            fold = Fold(
                fold_id=fold_id,
                train_start=train_start_ms,
                train_end=current_train_end,
                val_start=current_train_end,
                val_end=current_train_end + val_ms,
            )
            folds.append(fold)
            fold_id += 1

        current_train_end += step_ms

    if not folds:
        raise ValueError(
            f"Dataset range [{dataset_start}, {dataset_end}] is too short "
            f"for train_window={train_window_days}d, val_window={val_window_days}d"
        )

    return folds
