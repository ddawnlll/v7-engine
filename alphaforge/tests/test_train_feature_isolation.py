"""Regression tests for specialist alpha-family feature isolation."""

from __future__ import annotations

from alphaforge.train import build_aligned_training_frame, generate_synthetic_ohlcv


def test_returns_specialist_does_not_receive_residual_momentum_features():
    """An explicit returns-only experiment must not contain ``cs_*`` columns."""
    ohlcv = generate_synthetic_ohlcv(
        n_bars=160,
        symbols=("BTCUSDT", "ETHUSDT"),
        random_seed=7,
    )

    frame = build_aligned_training_frame(
        ohlcv,
        mode="SCALP",
        feature_groups=["returns"],
    )

    assert frame["X"].shape[0] > 0
    assert frame["feature_names"]
    assert not any(name.startswith("cs_") for name in frame["feature_names"])
