"""Regime-based training experiment with proper purged walk-forward.

Uses real purge/embargo gaps, epoch timestamps, cost-honest labels,
regime-specific threshold optimization, and regime expert ensemble.
"""

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "alphaforge/src")

PANEL_DIR = "/root/v7-engine/cache/v7_lite_expanded_panel_v1"


def load_data():
    close_df = pd.read_parquet(f"{PANEL_DIR}/panel_v7lite_expanded_close.parquet")
    ohlcv = {}
    for f in ["close", "high", "low", "open", "volume"]:
        ohlcv[f] = pd.read_parquet(f"{PANEL_DIR}/panel_v7lite_expanded_{f}.parquet")[f].values.astype(np.float64)
    ohlcv["symbol"] = close_df["symbol"].values
    ohlcv["timestamp"] = close_df["timestamp"].values.astype(np.int64)
    return ohlcv


def compute_vol_regime(ohlcv, n):
    close_all = ohlcv["close"]
    symbols = ohlcv["symbol"]
    unique_syms = sorted(set(symbols))
    regime_all = np.zeros(len(close_all), dtype=int)
    for sym in unique_syms:
        mask = symbols == sym
        sc = close_all[mask]
        atr = np.full(len(sc), np.nan)
        for i in range(14, len(sc)):
            atr[i] = np.mean(np.abs(np.diff(sc[max(0, i - 14) : i + 1])))
        ap = atr / (sc + 1e-10)
        v = ~np.isnan(ap)
        if v.sum() > 100:
            p33, p67 = np.percentile(ap[v], 33), np.percentile(ap[v], 67)
            sr = np.where(ap < p33, 1, np.where(ap < p67, 2, 3))
            regime_all[mask] = sr
    return regime_all[:n]


def run():
    from alphaforge.train import build_aligned_training_frame, _get_training_config
    from alphaforge.training.xgb_trainer import XGBoostTrainer
    from xgboost import XGBClassifier

    mode = "SCALP"
    print("[1] Building features...")
    ohlcv = load_data()
    tf = build_aligned_training_frame(ohlcv, mode)
    X = np.nan_to_num(tf["X"], nan=0.0)
    y_int, action_net_r, timestamps = tf["y_int"], tf["action_net_r"], tf["timestamps"]
    n = X.shape[0]
    print("    %d features, %d samples" % (X.shape[1], n))

    regime_aligned = compute_vol_regime(ohlcv, n)
    print("[2] Regime: LOW=%d MED=%d HIGH=%d" % (
        int(np.sum(regime_aligned == 1)), int(np.sum(regime_aligned == 2)), int(np.sum(regime_aligned == 3))))

    fold_size, purge, embargo = n // 7, n // 28, n // 56
    all_p, all_y, all_pm, all_ts, all_r, all_re = [], [], [], [], [], []
    print("[3] Purged WFV (6 folds)...")
    for k in range(6):
        te, vs, ve = (k + 2) * fold_size, (k + 2) * fold_size + purge + embargo, min((k + 2) * fold_size + purge + embargo + fold_size, n)
        if ve - vs < 100: continue
        X_tr, y_tr, X_val, y_val = X[:te], y_int[:te], X[vs:ve], y_int[vs:ve]
        from alphaforge.training.xgb_trainer import XGBoostTrainer
        result = XGBoostTrainer(mode=mode).train(X_tr, y_tr)
        proba = result.model.inplace_predict(X_val)
        preds = np.argmax(proba, axis=1)
        all_p.append(preds); all_y.append(y_val); all_pm.append(np.max(proba, axis=1))
        all_ts.append(timestamps[vs:ve]); all_r.append(action_net_r[vs:ve]); all_re.append(regime_aligned[vs:ve])
        print("    Fold %d: acc=%.4f LOW=%d MED=%d HIGH=%d" % (k+1, np.mean(preds==y_val), int(np.sum(regime_aligned[vs:ve]==1)), int(np.sum(regime_aligned[vs:ve]==2)), int(np.sum(regime_aligned[vs:ve]==3))))

    preds, yv, pm = np.concatenate(all_p), np.concatenate(all_y), np.concatenate(all_pm)
    ts_all, r_all, re_all = np.concatenate(all_ts), np.concatenate(all_r), np.concatenate(all_re)
    n_days = len(set(ts_all // 86400000))
    print("    OOS: %d samples, %d unique days" % (len(preds), n_days))

    # Global sweep
    print("\n  GLOBAL THRESHOLD SWEEP")
    print("  Th      N  Daily Day%% Win%%     NetR")
    for th in [0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
        act = (pm > th) & (preds != 2)
        na = int(act.sum())
        if na == 0: continue
        print("  %5.2f %6d %5.1f %5.1f %5.1f %9.6f" % (th, na, na/max(n_days,1), len(set(ts_all[act]//86400000))/max(n_days,1)*100, float(np.mean(preds[act]==yv[act]))*100, float(np.mean(r_all[act]))))

    # Regime-specific sweep
    print("\n  REGIME-SPECIFIC")
    for rid, rn in [(1,"LOW"), (2,"MED"), (3,"HIGH")]:
        for th in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
            act = (pm > th) & (preds != 2) & (re_all == rid)
            na = int(act.sum())
            if na == 0: continue
            print("  %-4s %4.2f %6d %5.1f %5.1f %5.1f %9.6f" % (rn, th, na, na/max(n_days,1), len(set(ts_all[act]//86400000))/max(n_days,1)*100, float(np.mean(preds[act]==yv[act]))*100, float(np.mean(r_all[act]))))

    # Regime expert
    print("\n  REGIME EXPERT ENSEMBLE (fold 1)")
    te, vs, ve = 2*fold_size, 2*fold_size+purge+embargo, min(2*fold_size+purge+embargo+fold_size, n)
    if ve-vs >= 100:
        from alphaforge.training.xgb_trainer import XGBoostTrainer
        for rid, rn in [(1,"LOW"), (2,"MED"), (3,"HIGH")]:
            rmask_tr = regime_aligned[:te] == rid
            if rmask_tr.sum() < 50: continue
            result_r = XGBoostTrainer(mode=mode).train(X[:te][rmask_tr], y_int[:te][rmask_tr])
            rmask_val = regime_aligned[vs:ve] == rid
            if rmask_val.sum() < 10: continue
            proba_r = result_r.model.inplace_predict(X[vs:ve][rmask_val])
            max_p_r = np.max(proba_r, axis=1)
            for th in [0.50, 0.60, 0.70]:
                na = int(np.sum(max_p_r > th))
                if na == 0: continue
                print("    %s th=%.1f: N=%d, win=%.1f%%" % (rn, th, na, float(np.mean(np.argmax(proba_r[max_p_r>th], axis=1) == y_int[vs:ve][rmask_val][max_p_r>th]))*100))

    print("\nDone.")


if __name__ == "__main__":
    run()
