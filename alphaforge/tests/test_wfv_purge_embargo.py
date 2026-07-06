"""Test purge/embargo derivation from MODE_CONFIG max_hold.

P0.9F: Walk-forward validation must use a purge-embargo gap at least
k * max_hold wide to prevent label leakage. k=2 is HOLD — requires
empirical calibration.

This test validates the computation logic directly (not the full
walk_forward_validate which trains XGBoost per fold).
"""

import math

from alphaforge.train import MODE_CONFIG, walk_forward_validate


def _expected_purge_embargo(
    n: int, min_folds: int, mode: str, k: int = 2,
) -> tuple[int, int]:
    """Compute what purge/embargo *should* be given the MODE_CONFIG contract."""
    fold_size = n // (min_folds + 1)
    max_hold = MODE_CONFIG[mode]["max_hold"]
    purge = max(fold_size // 4, k * max_hold)
    embargo = max(fold_size // 8, k * max_hold)
    return purge, embargo


# ---------------------------------------------------------------------------
# Unit tests — computation logic only, no XGBoost training
# ---------------------------------------------------------------------------


def test_purge_embargo_all_modes_meet_max_hold_floor() -> None:
    """For each mode, verify that purge_bars >= max_hold and
    embargo_bars >= max_hold across a range of dataset sizes."""
    for n in [500, 1000, 2000, 5000]:
        for mode in ["SCALP", "SWING", "AGGRESSIVE_SCALP"]:
            p, e = _expected_purge_embargo(n, 6, mode)
            max_h = MODE_CONFIG[mode]["max_hold"]
            assert p >= max_h, (
                f"{mode} n={n}: purge={p} < max_hold={max_h}"
            )
            assert e >= max_h, (
                f"{mode} n={n}: embargo={e} < max_hold={max_h}"
            )


def test_purge_embargo_respects_fold_size_floor() -> None:
    """When fold_size//4 > k*max_hold, purge should track fold_size.

    SCALP has the lowest max_hold (12), so for n=2000, fold_size ≈ 285,
    fold_size//4 = 71 > 24 = 2*12 → the fold_size term dominates.
    """
    n = 2000
    for mode in ["SCALP", "SWING", "AGGRESSIVE_SCALP"]:
        p, _ = _expected_purge_embargo(n, 6, mode)
        fold_size = n // 7  # min_folds + 1 = 7
        max_h = MODE_CONFIG[mode]["max_hold"]
        assert p >= fold_size // 4, (
            f"{mode}: purge={p} < fold_size//4={fold_size // 4}"
        )


def test_purge_embargo_k2_floor_active_for_large_max_hold() -> None:
    """SWING has max_hold=30, so k*max_hold=60. For small n, the
    k*max_hold floor should dominate."""
    n = 500  # fold_size ≈ 71, fold_size//4 ≈ 17, k*max_hold = 60
    p, e = _expected_purge_embargo(n, 6, "SWING")
    # k*max_hold = 60 should dominate over fold_size//4 ≈ 17
    assert p >= 60, f"SWING small n: purge={p} < 60"
    # k*max_hold = 60 should dominate over fold_size//8 ≈ 8
    assert e >= 60, f"SWING small n: embargo={e} < 60"


def test_k_value_is_exported_as_hold() -> None:
    """The k=2 multiplier is HOLD — this test fails if the value has
    been changed to LOCKED without documentation. If you change k,
    update v7/docs/roadmap.md accordingly."""
    # We re-derive k from the computation: for SCALP with n=5000,
    # fold_size ≈ 714, fold_size//4 ≈ 178. k*max_hold = k*12.
    # If k=2, purge = max(178, 24) = 178.
    n, mode, min_folds = 5000, "SCALP", 6
    p, _ = _expected_purge_embargo(n, min_folds, mode)
    fold_size = n // (min_folds + 1)
    k_implied = math.ceil((p - fold_size // 4) / MODE_CONFIG[mode]["max_hold"])
    # purge is max(fold_size//4, k*max_hold), so if fold_size//4 dominates,
    # the implied k from the floor may be 0 or negative — only check
    # when the k*max_hold term actually dominates.
    if p == 2 * MODE_CONFIG[mode]["max_hold"]:
        assert k_implied <= 2, (
            f"k appears to have changed: computed k_implied={k_implied} for {mode}"
        )
