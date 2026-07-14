"""Hybrid ensemble: global model + per-symbol specialist + regime filter.
The global model provides direction. The per-symbol specialist provides confidence.
Regime filter provides context. Only take trades where ALL three agree."""
import sys, numpy as np, pandas as pd, time
sys.path.insert(0, "alphaforge/src")

PANEL = "/root/v7-engine/cache/v7_lite_expanded_panel_v1"

def run():
    from alphaforge.train import build_aligned_training_frame, _get_training_config
    from alphaforge.training.xgb_trainer import XGBoostTrainer

    ohlcv = {}
    close_df = pd.read_parquet(f"{PANEL}/panel_v7lite_expanded_close.parquet")
    for f in ["close","high","low","open","volume"]:
        ohlcv[f] = pd.read_parquet(f"{PANEL}/panel_v7lite_expanded_{f}.parquet")[f].values.astype(np.float64)
    ohlcv["symbol"] = close_df["symbol"].values
    ohlcv["timestamp"] = close_df["timestamp"].values.astype(np.int64)

    print("[1] Building features...")
    tf = build_aligned_training_frame(ohlcv, "SCALP")
    X = np.nan_to_num(tf["X"], nan=0.0)
    y_int, action_net_r, timestamps = tf["y_int"], tf["action_net_r"], tf["timestamps"]
    symbols = tf["symbols"]
    n = X.shape[0]
    print("    %d features, %d samples" % (X.shape[1], n))

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

    print("[2] Hybrid ensemble WFV (6 folds)...")
    t0 = time.time()
    all_preds, all_y, all_pm, all_ts, all_r, all_re = [], [], [], [], [], []

    for k in range(6):
        te = (k+2)*fold_size; vs = te+purge+embargo; ve = min(vs+fold_size, n)
        if ve-vs < 100: continue
        X_tr, y_tr = X[:te], y_int[:te]

        # 1. Global model
        result_global = XGBoostTrainer(mode="SCALP").train(X_tr, y_tr)
        X_val = X[vs:ve]
        proba_global = result_global.model.inplace_predict(X_val)
        preds_global = np.argmax(proba_global, axis=1)
        conf_global = np.max(proba_global, axis=1)

        # 2. Per-symbol specialist models
        unique_syms = np.unique(symbols[:te])
        symbol_models = {}
        for sym in unique_syms:
            sym_mask = symbols[:te] == sym
            if sym_mask.sum() < 100: continue
            try:
                result_sym = XGBoostTrainer(mode="SCALP").train(X[:te][sym_mask], y_int[:te][sym_mask])
                symbol_models[sym] = result_sym.model
            except: pass

        # 3. Per-symbol predictions on OOS
        sym_val = symbols[vs:ve]
        preds_sym = np.full(len(X_val), 2, dtype=np.int32)
        proba_sym = np.full((len(X_val), 3), 1.0/3)
        for sym, model in symbol_models.items():
            sym_mask_val = sym_val == sym
            if sym_mask_val.sum() == 0: continue
            proba_sym[sym_mask_val] = model.inplace_predict(X_val[sym_mask_val])
            preds_sym[sym_mask_val] = np.argmax(proba_sym[sym_mask_val], axis=1)

        # 4. Regime
        regime_val = regime_aligned[vs:ve]

        # 5. HYBRID: both models must agree on direction AND high confidence
        consensus = (preds_global == preds_sym) & (preds_global != 2)
        high_conf_global = conf_global > 0.55
        high_conf_sym = np.max(proba_sym, axis=1) > 0.55
        regime_mask = regime_val == 3  # HIGH vol

        # Strategy 1: consensus + high confidence
        hybrid_mask_1 = consensus & high_conf_global & high_conf_sym
        # Strategy 2: consensus + high confidence + HIGH regime
        hybrid_mask_2 = consensus & high_conf_global & high_conf_sym & regime_mask
        # Strategy 3: consensus + high confidence (any regime)
        hybrid_mask_3 = consensus & high_conf_global & high_conf_sym
        # Strategy 4: global confident + regime filter
        hybrid_mask_4 = high_conf_global & (preds_global != 2) & regime_mask
        # Strategy 5: global confident + symbol specialist agreed
        hybrid_mask_5 = high_conf_global & (preds_global == preds_sym) & (preds_global != 2)
        # Strategy 6: global confident + symbol confident (no regime)
        hybrid_mask_6 = high_conf_global & high_conf_sym & (preds_global != 2)

        # Store raw preds for strategy evaluation
        all_preds.append(preds_global)
        all_y.append(y_int[vs:ve])
        all_pm.append(conf_global)
        all_ts.append(timestamps[vs:ve])
        all_r.append(action_net_r[vs:ve])
        all_re.append(regime_val)

        print("    Fold %d: global_acc=%.4f sym_models=%d" % (
            k+1, np.mean(preds_global==y_int[vs:ve]), len(symbol_models)))

    preds = np.concatenate(all_preds); yv = np.concatenate(all_y); pm = np.concatenate(all_pm)
    ts_all = np.concatenate(all_ts); r_all = np.concatenate(all_r); re_all = np.concatenate(all_re)
    n_days = len(set(ts_all // 86400000))
    print("    WFV: %.0fs" % (time.time()-t0))
    print("    OOS: %d samples, %d days" % (len(preds), n_days))

    # Evaluate each strategy
    strategies = {
        "A: Global only": (pm > 0.70) & (preds != 2),
        "B: Global + HIGH regime": (pm > 0.55) & (preds != 2) & (re_all == 3),
        "C: Global + LOW regime": (pm > 0.55) & (preds != 2) & (re_all == 1),
    }

    print("\n=== STRATEGY COMPARISON ===")
    print("%-30s %6s %7s %6s %5s %9s" % ("Strategy", "N", "Daily", "Day%%", "Win%%", "NetR"))
    print("-" * 70)
    for name, mask in strategies.items():
        na = int(mask.sum())
        if na == 0: continue
        dr = na/max(n_days,1)
        wr = float(np.mean(preds[mask]==yv[mask]))
        rm = float(np.mean(r_all[mask]))
        ad = len(set(ts_all[mask]//86400000))
        print("%-30s %6d %7.1f %5.1f%% %5.1f%% %9.6f" % (name, na, dr, ad/max(n_days,1)*100, wr*100, rm))

    print("\nDone.")

if __name__ == "__main__":
    run()
