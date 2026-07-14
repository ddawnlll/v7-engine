"""Regime experiment v2: Lower threshold + regime filter to get N>=200 trades at th=0.70 equivalent."""
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
    n = X.shape[0]
    print("    %d features, %d samples" % (X.shape[1], n))

    # Regime
    close_all, symbols = ohlcv["close"], ohlcv["symbol"]
    regime_all = np.zeros(len(close_all), dtype=int)
    for sym in sorted(set(symbols)):
        mask = symbols == sym
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
    all_p, all_y, all_pm, all_ts, all_r, all_re = [], [], [], [], [], []

    print("[2] Purged WFV (6 folds)...")
    t0 = time.time()
    for k in range(6):
        te = (k+2)*fold_size; vs = te+purge+embargo; ve = min(vs+fold_size, n)
        if ve-vs < 100: continue
        X_tr, y_tr = X[:te], y_int[:te]
        X_val, y_val = X[vs:ve], y_int[vs:ve]
        result = XGBoostTrainer(mode="SCALP").train(X_tr, y_tr)
        proba = result.model.inplace_predict(X_val)
        preds = np.argmax(proba, axis=1)
        all_p.append(preds); all_y.append(y_val); all_pm.append(np.max(proba, axis=1))
        all_ts.append(timestamps[vs:ve]); all_r.append(action_net_r[vs:ve])
        all_re.append(regime_aligned[vs:ve])
        print("    Fold %d: acc=%.4f" % (k+1, np.mean(preds==y_val)))
    print("    WFV: %.0fs" % (time.time()-t0))

    preds = np.concatenate(all_p); yv = np.concatenate(all_y); pm = np.concatenate(all_pm)
    ts_all = np.concatenate(all_ts); r_all = np.concatenate(all_r); re_all = np.concatenate(all_re)
    n_days = len(set(ts_all // 86400000))
    print("    OOS: %d samples, %d days" % (len(preds), n_days))

    # Strategy A: Simple threshold sweep
    print("\n=== STRATEGY A: Global Threshold Sweep ===")
    print("Th     N      Daily  Day%%  Win%%    NetR    2xR")
    for th in [0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70]:
        act = (pm > th) & (preds != 2)
        na = int(act.sum())
        if na == 0: continue
        dr = na/max(n_days,1)
        wr = float(np.mean(preds[act]==yv[act]))
        rm = float(np.mean(r_all[act]))
        ad = len(set(ts_all[act]//86400000))
        print("%4.2f %6d %7.1f %5.1f%% %5.1f%% %7.5f %7.5f" % (th, na, dr, ad/max(n_days,1)*100, wr*100, rm, rm*2))

    # Strategy B: Lower threshold + high-confidence filter
    # Use th=0.50 but only accept when confidence spread is large
    print("\n=== STRATEGY B: th=0.50 + Confidence Spread Filter ===")
    # confidence spread = max proba - median of other 2 classes
    proba_3class = np.zeros((len(pm), 3))
    for k_idx in range(6):
        te = (k_idx+2)*fold_size; vs = te+purge+embargo; ve = min(vs+fold_size, n)
        if ve-vs < 100: continue
        X_val = X[vs:ve]
        # Reconstruct from stored data
        pass  # We already have preds and pm

    # Strategy C: th=0.50 + regime filter (HIGH vol only)
    print("\n=== STRATEGY C: th=0.50 + HIGH Vol Regime Only ===")
    for th in [0.30, 0.40, 0.50, 0.55, 0.60]:
        act = (pm > th) & (preds != 2) & (re_all == 3)
        na = int(act.sum())
        if na == 0: continue
        dr = na/max(n_days,1)
        wr = float(np.mean(preds[act]==yv[act]))
        rm = float(np.mean(r_all[act]))
        ad = len(set(ts_all[act]//86400000))
        print("%4.2f %6d %7.1f %5.1f%% %5.1f%% %7.5f %7.5f" % (th, na, dr, ad/max(n_days,1)*100, wr*100, rm, rm*2))

    # Strategy D: th=0.50 + LOW vol filter (mean-reversion regime)
    print("\n=== STRATEGY D: th=0.50 + LOW Vol Regime Only ===")
    for th in [0.30, 0.40, 0.50, 0.55, 0.60]:
        act = (pm > th) & (preds != 2) & (re_all == 1)
        na = int(act.sum())
        if na == 0: continue
        dr = na/max(n_days,1)
        wr = float(np.mean(preds[act]==yv[act]))
        rm = float(np.mean(r_all[act]))
        ad = len(set(ts_all[act]//86400000))
        print("%4.2f %6d %7.1f %5.1f%% %5.1f%% %7.5f %7.5f" % (th, na, dr, ad/max(n_days,1)*100, wr*100, rm, rm*2))

    # Strategy E: Dynamic threshold - adaptive based on recent win rate
    print("\n=== STRATEGY E: Adaptive Threshold (rolling 100-trade window) ===")
    # Simulate: at each point, adjust threshold based on recent performance
    adaptive_th = np.full(len(pm), 0.50)
    window = 100
    recent_wr = []
    adaptive_preds = []
    for i in range(len(pm)):
        if i >= window:
            recent_wr.append(float(np.mean(np.array(adaptive_preds[-window:]) == np.array(yv[-window:]))))
            if len(recent_wr) > 1 and recent_wr[-1] > 0.60:
                adaptive_th[i] = min(0.70, adaptive_th[i] + 0.01)
            elif recent_wr[-1] < 0.45:
                adaptive_th[i] = max(0.30, adaptive_th[i] - 0.01)
        adaptive_preds.append(preds[i])
    act_adaptive = (pm > adaptive_th) & (preds != 2)
    na = int(act_adaptive.sum())
    if na > 0:
        dr = na/max(n_days,1)
        wr = float(np.mean(preds[act_adaptive]==yv[act_adaptive]))
        rm = float(np.mean(r_all[act_adaptive]))
        ad = len(set(ts_all[act_adaptive]//86400000))
        print("Adaptive: N=%d, Daily=%5.1f, Day%%=%5.1f%%, Win=%5.1f%%, NetR=%7.5f" % (na, dr, ad/max(n_days,1)*100, wr*100, rm))

    # Strategy F: Symbol-level specialist (train per-symbol, test globally)
    print("\n=== STRATEGY F: Symbol-Level Specialist (best 10 symbols) ===")
    # This would require per-symbol training - skip for now, just report
    print("    (Requires per-symbol WFV - next iteration)")

    print("\nDone.")

if __name__ == "__main__":
    run()
