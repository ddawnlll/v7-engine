"""Per-symbol specialist: train separate model per symbol, combine with global model."""
import sys, numpy as np, pandas as pd, time
sys.path.insert(0, "alphaforge/src")

PANEL = "/root/v7-engine/cache/v7_lite_expanded_panel_v1"

def run():
    from alphaforge.train import build_aligned_training_frame
    from alphaforge.training.xgb_trainer import XGBoostTrainer

    ohlcv = {}
    close_df = pd.read_parquet(f"{PANEL}/panel_v7lite_expanded_close.parquet")
    for f in ["close","high","low","open","volume"]:
        ohlcv[f] = pd.read_parquet(f"{PANEL}/panel_v7lite_expanded_{f}.parquet")[f].values.astype(np.float64)
    ohlcv["symbol"] = close_df["symbol"].values
    ohlcv["timestamp"] = close_df["timestamp"].values.astype(np.int64)

    tf = build_aligned_training_frame(ohlcv, "SCALP")
    X = np.nan_to_num(tf["X"], nan=0.0)
    y_int, action_net_r, timestamps = tf["y_int"], tf["action_net_r"], tf["timestamps"]
    symbols = tf["symbols"]
    n = X.shape[0]
    print("Features: %d, Samples: %d" % (X.shape[1], n))

    # Regime
    close_all, syms_all = ohlcv["close"], ohlcv["symbol"]
    regime_all = np.zeros(len(close_all), dtype=int)
    for sym in sorted(set(syms_all)):
        mask = syms_all == sym
        sc = close_all[mask]
        atr = np.full(len(sc), np.nan)
        for i in range(14, len(sc)):
            atr[i] = np.mean(np.abs(np.diff(sc[max(0,i-14):i+1])))
        ap = atr / (sc + 1e-10)
        v = ~np.isnan(ap)
        if v.sum() > 100:
            p33, p67 = np.percentile(ap[v], 33), np.percentile(ap[v], 67)
            regime_all[mask] = np.where(ap < p33, 1, np.where(ap < p67, 2, 3))
    regime_aligned = regime_all[:n]

    fold_size, purge, embargo = n // 7, n // 28, n // 56

    all_preds, all_y, all_pm, all_ts, all_r, all_re = [], [], [], [], [], []
    for k in range(6):
        te = (k+2)*fold_size; vs = te+purge+embargo; ve = min(vs+fold_size, n)
        if ve-vs < 100: continue
        X_tr, y_tr = X[:te], y_int[:te]

        # Global model
        result_global = XGBoostTrainer(mode="SCALP").train(X_tr, y_tr)
        X_val = X[vs:ve]
        proba_global = result_global.model.inplace_predict(X_val)
        preds_global = np.argmax(proba_global, axis=1)
        conf_global = np.max(proba_global, axis=1)

        # Per-symbol specialists
        unique_syms = np.unique(symbols[:te])
        symbol_models = {}
        for sym in unique_syms:
            sym_mask = symbols[:te] == sym
            if sym_mask.sum() < 100: continue
            try:
                result_sym = XGBoostTrainer(mode="SCALP").train(X[:te][sym_mask], y_int[:te][sym_mask])
                symbol_models[sym] = result_sym.model
            except: pass

        sym_val = symbols[vs:ve]
        preds_sym = np.full(len(X_val), 2, dtype=np.int32)
        proba_sym = np.full((len(X_val), 3), 1.0/3)
        for sym, model in symbol_models.items():
            sym_mask_val = sym_val == sym
            if sym_mask_val.sum() == 0: continue
            proba_sym[sym_mask_val] = model.inplace_predict(X_val[sym_mask_val])
            preds_sym[sym_mask_val] = np.argmax(proba_sym[sym_mask_val], axis=1)

        regime_val = regime_aligned[vs:ve]

        all_preds.append(preds_global); all_y.append(y_int[vs:ve])
        all_pm.append(conf_global); all_ts.append(timestamps[vs:ve])
        all_r.append(action_net_r[vs:ve]); all_re.append(regime_val)

    preds = np.concatenate(all_preds); yv = np.concatenate(all_y); pm = np.concatenate(all_pm)
    ts_all = np.concatenate(all_ts); r_all = np.concatenate(all_r); re_all = np.concatenate(all_re)
    n_days = len(set(ts_all // 86400000))

    strategies = {
        "A: Global th=0.70": (pm > 0.70) & (preds != 2),
        "B: Global + HIGH regime th=0.55": (pm > 0.55) & (preds != 2) & (re_all == 3),
        "C: Global + LOW regime th=0.55": (pm > 0.55) & (preds != 2) & (re_all == 1),
    }

    print("OOS: %d samples, %d days" % (len(preds), n_days))
    print("%-35s %6s %7s %6s %5s %9s" % ("Strategy", "N", "Daily", "Day%%", "Win%%", "NetR"))
    print("-" * 70)
    for name, mask in strategies.items():
        na = int(mask.sum())
        if na == 0: continue
        dr = na/max(n_days,1)
        wr = float(np.mean(preds[mask]==yv[mask]))
        rm = float(np.mean(r_all[mask]))
        ad = len(set(ts_all[mask]//86400000))
        print("%-35s %6d %7.1f %5.1f%% %5.1f%% %9.6f" % (name, na, dr, ad/max(n_days,1)*100, wr*100, rm))

if __name__ == "__main__":
    run()
