"""Alpha candidate: momentum + mean-reversion hybrid.

Combines a 20-day rolling mean of daily returns (momentum) with a 5-day
rolling z-score of price relative to its 20-day mean (mean-reversion).

    alpha = 0.5 * momentum_signal - 0.5 * mean_reversion_signal

The minus sign on the mean-reversion term encodes the reversal hypothesis:
when price is far above its rolling mean (positive z-score) the signal is
to short, and vice versa.
"""

from __future__ import annotations

import pandas as pd


class MomentumMeanReversionAlpha:
    """Deterministic alpha combining momentum and mean-reversion signals.

    Parameters
    ----------
    momentum_window : int
        Rolling window (days) for the momentum factor — mean of daily returns.
    zscore_window : int
        Rolling window (days) for the price z-score computation (mean-reversion).
    mean_reversion_window : int
        Rolling window (days) for the mean-reversion z-score.
        Currently unused directly — the z-score uses zscore_window for both
        mean and std — kept as a named parameter for future tuning.
    """

    def __init__(
        self,
        momentum_window: int = 20,
        zscore_window: int = 20,
        mean_reversion_window: int = 5,
    ) -> None:
        self.momentum_window = momentum_window
        self.zscore_window = zscore_window
        self.mean_reversion_window = mean_reversion_window

    # ── Component signals (public for inspection / testing) ──────────

    def momentum_signal(self, data: pd.DataFrame) -> pd.Series:
        """20-day rolling mean of daily returns.

        Parameters
        ----------
        data : pd.DataFrame
            Must contain a 'returns' column.

        Returns
        -------
        pd.Series
            Rolling mean return, NaN for the first (momentum_window - 1) entries.
        """
        return data["returns"].rolling(self.momentum_window).mean()

    def mean_reversion_signal(self, data: pd.DataFrame) -> pd.Series:
        """5-day rolling z-score of close relative to its 20-day rolling mean.

        z = (close - rolling_mean) / rolling_std

        A high positive value means price is stretched above its recent mean,
        signalling a potential reversal downward.

        Parameters
        ----------
        data : pd.DataFrame
            Must contain a 'close' column.

        Returns
        -------
        pd.Series
            Z-score, NaN for the first (zscore_window - 1) entries.
        """
        rolling_mean = data["close"].rolling(self.zscore_window).mean()
        rolling_std = data["close"].rolling(self.zscore_window).std()
        # Guard against zero-std degenerate case
        rolling_std = rolling_std.replace(0, pd.NA)
        return (data["close"] - rolling_mean) / rolling_std

    # ── Combined signal ─────────────────────────────────────────────

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Generate combined alpha signals.

        alpha = 0.5 * momentum_signal - 0.5 * mean_reversion_signal

        Parameters
        ----------
        data : pd.DataFrame
            DataFrame with columns ``['close', 'returns']``, indexed by
            timestamp.  ``returns`` should be daily returns.

        Returns
        -------
        pd.Series
            Alpha signals aligned to the input index.  The first
            ``max(momentum_window, zscore_window) - 1`` entries are NaN
            (warm-up period).
        """
        momentum = self.momentum_signal(data)
        mean_rev = self.mean_reversion_signal(data)
        return 0.5 * momentum - 0.5 * mean_rev
