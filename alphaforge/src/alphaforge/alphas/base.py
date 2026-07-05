"""Abstract base class for alpha factors."""
from __future__ import annotations
from abc import ABC, abstractmethod
import pandas as pd

class AlphaBase(ABC):
    """Abstract base class for alpha factors."""
    direction: str = "long"

    @abstractmethod
    def compute(self, panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
        ...
