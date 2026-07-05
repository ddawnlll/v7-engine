"""21-day momentum alpha factor."""
from __future__ import annotations
import numpy as np
import pandas as pd
from alphaforge.alphas.base import AlphaBase

class AlphaMomentum(AlphaBase):
    """21-day momentum alpha: close.shift(21)/close - 1, z-scored cross-sectionally."""
    direction: str = "long"
    _window: int = 21

    def __init__(self, window: int = 21) -> None:
        self._window = window

    @property
    def window(self) -> int:
        return self._window

    def compute(self, panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
        close = panels.get("close")
        if close is None or close.empty:
            return pd.DataFrame()
        raw_scores = close.shift(self._window) / close - 1.0
        mean = raw_scores.mean(axis=1)
        std = raw_scores.std(axis=1).replace(0, np.nan)
        return raw_scores.sub(mean, axis=0).div(std, axis=0)
