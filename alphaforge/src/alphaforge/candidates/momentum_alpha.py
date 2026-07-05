"""20-day momentum alpha candidate: close(0) / close(20) - 1.

This is a pure deterministic momentum factor that measures the percentage
price change over the trailing 20 periods.  Positive values indicate upward
momentum (long signal), negative values indicate downward momentum (short
signal).
"""

from __future__ import annotations

import pandas as pd


class MomentumAlpha:
    """Deterministic 20-day momentum alpha.

    Signals are the 20-day lagged return: close(0) / close(20) - 1.

    Parameters
    ----------
    window : int
        Look-back window in periods (default 20).
    """

    def __init__(self, window: int = 20) -> None:
        self.window = window

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Generate momentum signals.

        Parameters
        ----------
        data : pd.DataFrame
            DataFrame with a ``close`` column, indexed by timestamp.

        Returns
        -------
        pd.Series
            Momentum signals: close(t) / close(t - window) - 1.
            The first ``window`` entries are NaN (warm-up).
        """
        if data.empty:
            return pd.Series(dtype=float)

        close = data["close"]
        signals = close / close.shift(self.window) - 1.0
        return signals
