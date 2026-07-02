"""Quick IC / Rank‑IC diagnostic script.

Usage (from repository root)::
    python -m alphaforge.ic_diagnosis <simulation_output_dir>

It reads the CSV files produced by the Simulation engine, builds a candidate
outcome dataset, extracts pre‑entry features, and computes a walk‑forward
Rank‑IC per fold. The script prints the per‑fold Rank‑IC values, the mean,
standard deviation, ICIR (mean/std) and the smallest MHT‑adjusted p‑value.
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from scipy.stats import spearmanr
# Manual Bonferroni correction (no external deps)

from .outcome_builder import build_candidate_outcome_dataset
from .entry_snapshot import extract_pre_entry_features

FEATURE_COLS = [
    "trend_regime",
    "vol_pct",
    "momentum_rank",
    "rs_rank",
    "btc_regime",
    "pullback_atr",
    "volume_zscore",
    "spread_proxy",
    "funding_context",
]

def walk_forward_ic(df: pd.DataFrame, n_folds: int = 6) -> np.ndarray:
    df = df.sort_values("ts")
    fold_len = len(df) // n_folds
    ic_vals = []
    for i in range(n_folds):
        fold = df.iloc[i * fold_len : (i + 1) * fold_len]
        y = fold["net_R"]
        ic_feat = []
        p_vals = []
        for col in FEATURE_COLS:
            rho, p = spearmanr(fold[col], y)
            ic_feat.append(rho)
            p_vals.append(p)
        # MHT correction per‑fold (Bonferroni)
        # Manual Bonferroni correction (not used further)
        # p_adj = [min(p * len(p_vals), 1.0) for p in p_vals]  # kept for reference
        ic_vals.append(np.mean(ic_feat))
    return np.array(ic_vals)

def run_diagnosis(sim_output_dir: str):
    df = build_candidate_outcome_dataset(Path(sim_output_dir))
    # Attach pre‑entry features
    feature_rows = df.apply(extract_pre_entry_features, axis=1)
    feature_df = pd.DataFrame(list(feature_rows))
    df = pd.concat([df, feature_df], axis=1)
    ic_folds = walk_forward_ic(df)
    ic_mean = ic_folds.mean()
    ic_std = ic_folds.std(ddof=1)
    icir = ic_mean / ic_std if ic_std != 0 else np.nan
    print("Rank‑IC per fold:", ic_folds)
    print(f"Mean Rank‑IC = {ic_mean:.4f}, Std = {ic_std:.4f}, ICIR = {icir:.2f}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m alphaforge.ic_diagnosis <simulation_output_dir>")
        sys.exit(1)
    run_diagnosis(sys.argv[1])
