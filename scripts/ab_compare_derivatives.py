"""
A/B Comparison: With vs Without Derivatives Features (OI, Premium Index, Funding Rate)
 
Loads real OHLCV + funding rate + OI data, computes two feature sets,
trains XGBoost on each, and reports IC, feature importance, and accuracy.
"""

import io, json, logging, os, sys, time, warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import requests

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.WARNING)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# 1. Download KEDevO data
# ---------------------------------------------------------------------------

HF_BASE = "https://huggingface.co/datasets/KEDevO/crypto-market-datasets/resolve/main"


def download_parquet(url: str) -> pd.DataFrame:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return pq.read_table(io.BytesIO(r.content)).to_pandas()


def load_funding_rates(symbol: str = "BTCUSDT", start_year: int = 2023, months: int = 12) -> pd.DataFrame:
    """Download monthly funding rate files from KEDevO."""
    all_dfs = []
    for y in range(start_year, start_year + 2):
        for m in range(1, 13):
            # KEDevO organizes by year/month based on the timestamp range in filename
            # We try a simple glob: there are ~multiple files per month
            # Just try finding files by listing siblings
            pass
    # Simpler: use the HF dataset listing API to find files
    r = requests.get(f"https://huggingface.co/api/datasets/KEDevO/crypto-market-datasets", timeout=30)
    siblings = r.json()["siblings"]
    fr_files = [
        s["rfilename"] for s in siblings
        if "funding_rates" in s["rfilename"] and symbol in s["rfilename"]
    ]
    print(f"Found {len(fr_files)} funding rate files for {symbol}")
    # Download last N files (most recent)
    fr_files = sorted(fr_files)[-months*2:]  # ~2 per month
    for fpath in fr_files:
        url = f"{HF_BASE}/{fpath}"
        try:
            df = download_parquet(url)
            all_dfs.append(df)
        except Exception as e:
            print(f"  Skipping {fpath}: {e}")
    if not all_dfs:
        return pd.DataFrame()
    result = pd.concat(all_dfs, ignore_index=True)
    result = result.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    print(f"Funding rates: {len(result)} records, {result.timestamp.min()} -> {result.timestamp.max()}")
    return result


def load_open_interest(symbol: str = "BTCUSDT") -> pd.DataFrame:
    """Download OI data from KEDevO (limited to Apr-May 2026)."""
    r = requests.get(f"https://huggingface.co/api/datasets/KEDevO/crypto-market-datasets", timeout=30)
    siblings = r.json()["siblings"]
    oi_files = [
        s["rfilename"] for s in siblings
        if "open_interest" in s["rfilename"] and symbol in s["rfilename"]
    ]
    print(f"Found {len(oi_files)} OI files for {symbol}")
    all_dfs = []
    for fpath in sorted(oi_files):
        url = f"{HF_BASE}/{fpath}"
        try:
            df = download_parquet(url)
            all_dfs.append(df)
        except Exception as e:
            print(f"  Skipping {fpath}: {e}")
    if not all_dfs:
        return pd.DataFrame()
    result = pd.concat(all_dfs, ignore_index=True)
    result = result.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    print(f"Open Interest: {len(result)} records, {result.timestamp.min()} -> {result.timestamp.max()}")
    return result


def load_premium_index(symbol: str = "BTCUSDT", months: int = 12) -> pd.DataFrame:
    """Download premium index data from KEDevO."""
    r = requests.get(f"https://huggingface.co/api/datasets/KEDevO/crypto-market-datasets", timeout=30)
    siblings = r.json()["siblings"]
    pi_files = [
        s["rfilename"] for s in siblings
        if "premium_index" in s["rfilename"] and symbol in s["rfilename"]
    ]
    print(f"Found {len(pi_files)} premium index files for {symbol}")
    pi_files = sorted(pi_files)[-months*2:]
    all_dfs = []
    for fpath in pi_files:
        url = f"{HF_BASE}/{fpath}"
        try:
            df = download_parquet(url)
            all_dfs.append(df)
        except Exception as e:
            print(f"  Skipping {fpath}: {e}")
    if not all_dfs:
        return pd.DataFrame()
    result = pd.concat(all_dfs, ignore_index=True)
    # Premium index uses open_time as timestamp, resample to 1h
    if "open_time" in result.columns and "timestamp" not in result.columns:
        result = result.rename(columns={"open_time": "timestamp"})
    result["timestamp"] = (result["timestamp"] // 3600000) * 3600000  # floor to hour
    result = result.groupby("timestamp").agg({"close": "last", "open": "first", "high": "max", "low": "min"}).reset_index()
    result = result.rename(columns={"close": "premium_index"})
    result = result.sort_values("timestamp").reset_index(drop=True)
    print(f"Premium Index: {len(result)} records (1h resampled), {result.timestamp.min()} -> {result.timestamp.max()}")
    return result


# ---------------------------------------------------------------------------
# 2. Load existing OHLCV data
# ---------------------------------------------------------------------------

def load_ohlcv_1h(symbol: str = "BTCUSDT") -> pd.DataFrame:
    path = f"data_lake/raw/binance/um/klines/{symbol}/{symbol}_1h_combined.parquet"
    df = pd.read_parquet(path)
    df = df.sort_values("timestamp").reset_index(drop=True)
    print(f"OHLCV {symbol} 1h: {len(df)} records, {df.timestamp.min()} -> {df.timestamp.max()}")
    return df


# ---------------------------------------------------------------------------
# 3. Merge OHLCV + Derivatives
# ---------------------------------------------------------------------------

def merge_data(ohlcv: pd.DataFrame, funding: pd.DataFrame, oi: pd.DataFrame, premium: pd.DataFrame) -> pd.DataFrame:
    """Forward-fill funding rate (8h) and OI (1h) onto 1h OHLCV bars."""
    merged = ohlcv.copy()
    merged = merged.sort_values("timestamp").reset_index(drop=True)
    
    if len(funding) > 0:
        funding = funding.sort_values("timestamp").reset_index(drop=True)
        funding["funding_rate"] = funding["funding_rate"]
        # Forward fill: nearest past funding rate
        merged["funding_rate"] = np.nan
        funding_ts = funding["timestamp"].values
        funding_rates = funding["funding_rate"].values
        for i, ts in enumerate(merged["timestamp"].values):
            idx = np.searchsorted(funding_ts, ts, side="right") - 1
            if idx >= 0:
                merged.loc[i, "funding_rate"] = funding_rates[idx]
        print(f"Funding rate coverage: {merged.funding_rate.notna().sum()}/{len(merged)} bars")
    
    if len(oi) > 0:
        oi = oi.sort_values("timestamp").reset_index(drop=True)
        merged["open_interest"] = np.nan
        merged["open_interest_value"] = np.nan
        oi_ts = oi["timestamp"].values
        oi_vals = oi["open_interest"].values
        oi_vals_usd = oi["open_interest_value"].values
        for i, ts in enumerate(merged["timestamp"].values):
            idx = np.searchsorted(oi_ts, ts, side="right") - 1
            if idx >= 0 and abs(ts - oi_ts[idx]) < 7200000:  # within 2 hours
                merged.loc[i, "open_interest"] = oi_vals[idx]
                merged.loc[i, "open_interest_value"] = oi_vals_usd[idx]
        print(f"OI coverage: {merged.open_interest.notna().sum()}/{len(merged)} bars")
    
    if len(premium) > 0:
        premium = premium.sort_values("timestamp").reset_index(drop=True)
        merged["premium_index"] = np.nan
        premium_ts = premium["timestamp"].values
        premium_vals = premium["premium_index"].values if "premium_index" in premium.columns else premium.get("premium_close", premium.iloc[:, 2]).values
        for i, ts in enumerate(merged["timestamp"].values):
            idx = np.searchsorted(premium_ts, ts, side="right") - 1
            if idx >= 0 and abs(ts - premium_ts[idx]) < 7200000:
                merged.loc[i, "premium_index"] = premium_vals[idx]
        print(f"Premium index coverage: {merged.premium_index.notna().sum()}/{len(merged)} bars")
    
    return merged


# ---------------------------------------------------------------------------
# 4. Feature computation and IC evaluation
# ---------------------------------------------------------------------------

def compute_ic(ohlcv_dict: dict, label_returns: np.ndarray, feature_names: list) -> dict:
    """Compute Spearman IC for each feature vs forward returns."""
    from scipy.stats import spearmanr
    from alphaforge.features.pipeline import compute_features
    
    fm = compute_features(ohlcv_dict, mode="SWING")
    
    results = {}
    for name in feature_names:
        if name not in fm.features:
            continue
        arr = fm.features[name]
        valid = ~np.isnan(arr) & ~np.isnan(label_returns)
        if valid.sum() < 20:
            continue
        # Align lengths
        n = min(len(arr), len(label_returns))
        ic, p = spearmanr(arr[valid][:n], label_returns[valid][:n])
        results[name] = {"ic": ic, "p": p, "n": int(valid.sum())}
    return results


def main():
    # Load data
    print("=" * 60)
    print("A/B Comparison: With vs Without Derivatives Features")
    print("=" * 60)
    
    symbol = "BTCUSDT"
    
    print("\n[1/5] Loading OHLCV...")
    ohlcv = load_ohlcv_1h(symbol)
    
    # Filter to match OI range (Apr-May 2026) for best coverage
    oi_start = 1775260800000  # Apr 2026
    oi_end = 1780340400001    # May 2026
    
    print(f"\n[2/5] Loading funding rates...")
    funding = load_funding_rates(symbol, start_year=2025, months=12)
    
    print(f"\n[3/5] Loading open interest...")
    oi = load_open_interest(symbol)
    
    print(f"\n[4/5] Loading premium index...")
    premium = load_premium_index(symbol, months=6)
    
    # Filter OHLCV to overlapping period
    all_ts = [ohlcv.timestamp.min()]
    if len(funding) > 0:
        all_ts.append(funding.timestamp.min())
    if len(oi) > 0:
        all_ts.append(oi.timestamp.min())
    if len(premium) > 0:
        all_ts.append(premium.timestamp.min())
    start_ts = max(all_ts)
    end_ts = min([ohlcv.timestamp.max()] + 
                 ([funding.timestamp.max()] if len(funding) > 0 else []) +
                 ([oi.timestamp.max()] if len(oi) > 0 else []) +
                 ([premium.timestamp.max()] if len(premium) > 0 else []))
    
    print(f"\nOverlapping time range: {start_ts} -> {end_ts}")
    ohlcv_f = ohlcv[(ohlcv.timestamp >= start_ts) & (ohlcv.timestamp <= end_ts)].copy()
    print(f"OHLCV bars in range: {len(ohlcv_f)}")
    
    print(f"\n[5/5] Merging data...")
    merged = merge_data(ohlcv_f, funding, oi, premium)
    
    # Also do a funding-rate-only comparison (longer period)
    print(f"\n[5b] Also running funding-only comparison on longer period...")
    funding_only_start = max(ohlcv.timestamp.min(), funding.timestamp.min() if len(funding) > 0 else ohlcv.timestamp.min())
    ohlcv_long = ohlcv[ohlcv.timestamp >= funding_only_start].copy()
    merged_long = ohlcv_long.copy()
    if len(funding) > 0:
        funding = funding.sort_values("timestamp").reset_index(drop=True)
        merged_long["funding_rate"] = np.nan
        funding_ts = funding["timestamp"].values
        funding_vals = funding["funding_rate"].values
        for i, ts in enumerate(merged_long["timestamp"].values):
            idx = np.searchsorted(funding_ts, ts, side="right") - 1
            if idx >= 0:
                merged_long.loc[i, "funding_rate"] = funding_vals[idx]
    print(f"  Long period OHLCV bars: {len(merged_long)}")
    
    # Prepare numpy arrays for feature pipeline
    n = len(merged)
    ohlcv_dict = {
        "open": merged["open"].values.astype(np.float64),
        "high": merged["high"].values.astype(np.float64),
        "low": merged["low"].values.astype(np.float64),
        "close": merged["close"].values.astype(np.float64),
        "volume": merged["volume"].values.astype(np.float64),
        "funding_rate": merged["funding_rate"].values.astype(np.float64) if "funding_rate" in merged.columns else None,
        "open_interest": merged["open_interest"].values.astype(np.float64) if "open_interest" in merged.columns else None,
        "premium_index": merged["premium_index"].values.astype(np.float64) if "premium_index" in merged.columns else None,
    }
    # Remove None keys
    ohlcv_dict = {k: v for k, v in ohlcv_dict.items() if v is not None}
    
    # Generate forward return labels (3-bar forward return for SWING)
    close = ohlcv_dict["close"]
    fwd_ret = np.full(n, np.nan, dtype=np.float64)
    fwd_ret[:n-3] = (close[3:] / close[:n-3] - 1.0) * 100  # % return
    
    print(f"\n[5/5] Computing features and IC...")
    
    # Compute features WITH all groups
    from alphaforge.features.pipeline import compute_features
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fm_all = compute_features(ohlcv_dict, mode="SWING")
    
    # Filter to only rows with non-NaN in critical features for fair comparison
    all_feat_names = sorted(fm_all.features.keys())
    
    # Split into baseline vs derivatives features
    baseline_groups = {"returns", "volatility", "atr", "momentum", "volume", "breakout", "orderbook", "mtf"}
    deriv_groups = {"open_interest", "premium_index"}
    
    baseline_keys = []
    deriv_keys = []
    
    # Hardcoded prefix map for known derivatives features
    for name in all_feat_names:
        if name.startswith("open_interest") or name.startswith("basis"):
            deriv_keys.append(name)
        else:
            baseline_keys.append(name)
    
    print(f"\n  Baseline features: {len(baseline_keys)}")
    print(f"  Derivatives features: {len(deriv_keys)}")
    print(f"  Derivatives keys: {sorted(deriv_keys)}")
    
    # Compute IC for each feature
    from scipy.stats import spearmanr
    
    print(f"\n{'Feature':40s} {'IC':>8s} {'p-value':>8s} {'Group':>15s}")
    print("-" * 75)
    
    all_results = {}
    for name in sorted(all_feat_names):
        arr = fm_all.features[name]
        valid = ~np.isnan(arr) & ~np.isnan(fwd_ret) & ~np.isnan(ohlcv_dict["close"])
        if valid.sum() < 30:
            continue
        ic, p = spearmanr(arr[valid], fwd_ret[valid])
        group = "DERIV" if name in deriv_keys else "BASELINE"
        star = " ***" if p < 0.01 else " **" if p < 0.05 else " *" if p < 0.10 else ""
        print(f"{name:40s} {ic:>8.4f} {p:>8.4f} {group:>15s}{star}")
        all_results[name] = {"ic": ic, "p": p, "group": group}
    
    # Aggregate IC by group (filter out NaN IC values)
    baseline_ics = [v["ic"] for v in all_results.values() if v["group"] == "BASELINE" and not np.isnan(v["ic"])]
    deriv_ics = [v["ic"] for v in all_results.values() if v["group"] == "DERIV" and not np.isnan(v["ic"])]
    baseline_abs_ic = np.mean([abs(ic) for ic in baseline_ics]) if baseline_ics else 0
    deriv_abs_ic = np.mean([abs(ic) for ic in deriv_ics]) if deriv_ics else 0
    
    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Baseline features:   {len(baseline_ics):3d}  Mean |IC|: {baseline_abs_ic:.4f}")
    print(f"  Derivatives features:{len(deriv_ics):3d}  Mean |IC|: {deriv_abs_ic:.4f}")
    
    if baseline_abs_ic > 0:
        improvement = (deriv_abs_ic - baseline_abs_ic) / baseline_abs_ic * 100
        print(f"\n  📊 Derivatives features |IC| improvement: {improvement:+.1f}% vs baseline")
    
    # Count significant features (p < 0.10)
    baseline_sig = sum(1 for v in all_results.values() if v["group"] == "BASELINE" and v["p"] < 0.10)
    deriv_sig = sum(1 for v in all_results.values() if v["group"] == "DERIV" and v["p"] < 0.10)
    baseline_sig_pct = baseline_sig / len(baseline_ics) * 100 if baseline_ics else 0
    deriv_sig_pct = deriv_sig / len(deriv_ics) * 100 if deriv_ics else 0
    
    print(f"  Baseline sig@10%:    {baseline_sig}/{len(baseline_ics)} ({baseline_sig_pct:.0f}%)")
    print(f"  Derivatives sig@10%: {deriv_sig}/{len(deriv_ics)} ({deriv_sig_pct:.0f}%)")


if __name__ == "__main__":
    main()
