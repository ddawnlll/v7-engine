# Extract pre‑entry observable features from a SimulationEntry
import pandas as pd

def extract_pre_entry_features(entry: pd.Series) -> dict:
    """Return a dict of features that are known at entry time.

    The keys correspond to the feature list used in the IC diagnostic.
    This function is deliberately lightweight – it only reads columns that
    exist in the SimulationOutput CSVs. If a column is missing, a NaN is
    returned, which the downstream IC calculation will handle.
    """
    return {
        "trend_regime": entry.get("trend_regime"),
        "vol_pct": entry.get("vol_pct"),
        "momentum_rank": entry.get("momentum_rank"),
        "rs_rank": entry.get("rs_rank"),
        "btc_regime": entry.get("btc_regime"),
        "pullback_atr": entry.get("pullback_atr"),
        "volume_zscore": entry.get("volume_zscore"),
        "spread_proxy": entry.get("spread_proxy"),
        "funding_context": entry.get("funding_context"),
    }
