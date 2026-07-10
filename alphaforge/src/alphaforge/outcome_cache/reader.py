"""Outcome cache reader: query cached outcomes by alpha_id, symbol, or filter."""

from pathlib import Path
import pandas as pd
from typing import Optional


class OutcomeCacheReader:
    """Query persisted outcome cache by alpha, symbol, or filter expression."""

    def __init__(self, base_path: str = "data/outcome_cache/v1"):
        self.base_path = Path(base_path)

    def _all_parquet_files(self) -> list[Path]:
        """Return all parquet files in the cache, sorted."""
        if not self.base_path.exists():
            return []
        return sorted(self.base_path.rglob("*.parquet"))

    def get_outcomes(
        self,
        alpha_id: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> pd.DataFrame:
        """Load outcomes, optionally filtered by alpha_id and/or symbol."""
        if symbol:
            sym_path = self.base_path / f"symbol={symbol}"
            if not sym_path.exists():
                return pd.DataFrame()
            files = sorted(sym_path.glob("*.parquet"))
        else:
            files = self._all_parquet_files()

        if not files:
            return pd.DataFrame()

        dfs = []
        for f in files:
            df = pd.read_parquet(f)
            if alpha_id:
                df = df[df["alpha_id"] == alpha_id]
            dfs.append(df)

        result = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
        return result

    def lookup(self, alpha_id: str, symbol: str, entry_bar: int) -> Optional[dict]:
        """O(1) lookup by primary key (alpha_id, symbol, entry_bar)."""
        outcomes = self.get_outcomes(alpha_id, symbol)
        if outcomes.empty:
            return None
        match = outcomes[outcomes["entry_bar"] == entry_bar]
        if match.empty:
            return None
        return match.iloc[0].to_dict()

    def query(self, filter_expr: str) -> pd.DataFrame:
        """Query all cached outcomes with a pandas query expression.

        Example: "alpha_id='discovery_pipeline_v6' AND net_R > 0.5"
        """
        df = self.get_outcomes()
        if df.empty:
            return df
        return df.query(filter_expr)

    def summary(self) -> dict:
        """Return summary statistics of the entire cache."""
        df = self.get_outcomes()
        if df.empty:
            return {"total_records": 0, "alphas": [], "symbols": [], "date_range": []}
        return {
            "total_records": len(df),
            "alphas": df["alpha_id"].unique().tolist(),
            "symbols": df["symbol"].unique().tolist(),
            "net_R_min": float(df["net_R"].min()),
            "net_R_max": float(df["net_R"].max()),
            "net_R_mean": float(df["net_R"].mean()),
            "date_range": [
                str(df["entry_time"].min()) if "entry_time" in df else "",
                str(df["entry_time"].max()) if "entry_time" in df else "",
            ],
        }

    def count_by_alpha(self) -> dict:
        """Return count of records per alpha_id."""
        df = self.get_outcomes()
        if df.empty:
            return {}
        return df["alpha_id"].value_counts().to_dict()

    def count_by_symbol(self, alpha_id: Optional[str] = None) -> dict:
        """Return count of records per symbol, optionally filtered by alpha."""
        df = self.get_outcomes(alpha_id=alpha_id)
        if df.empty:
            return {}
        return df["symbol"].value_counts().to_dict()
