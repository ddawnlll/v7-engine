"""Honest confidence boost: uses fc997b4 harness (build_aligned_training_frame,
real purge/embargo, cost-honest labels, epoch timestamps). Only temperature
scaling and feature pruning are tested as confidence boost methods."""
import sys, numpy as np, pandas as pd, time
sys.path.insert(0, 'alphaforge/src')

from xgboost import XGBClassifier
from alphaforge.train import build_aligned_training_frame, _get_training_config
from alphaforge.training.xgb_trainer import XGBoostTrainer

def softmax(logits, T=1.0):
    x = logits / T
    x -= np.max(x, axis=1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=1, keepdims=True)

def run():
    mode = 'SCALP'
    print('[1] Building features with fc997b4 harness...')
    t0 = time.time()
    ohlcv = {}
    close_df = pd.read_parquet('/root/v7-engine/cache/v7_lite_expanded_panel_v1/panel_v7lite_expanded_close.parquet')
    for f in ['close','high','low','open','volume']:
        ohlcv[f] = pd.read_parquet(f'/root/v7-engine/cache/v7_lite_expanded_panel_v1/panel_v7lite_expanded_{f}.parquet')[f].values.astype(np.float64)
    ohlcv['symbol'] = close_df['symbol'].values
    ohlcv['timestamp'] = close_df['timestamp'].values.astype(np.int64)

    tf = build_aligned_training_frame(ohlcv, mode)
    X = np.nan_to_num(tf['X'], nan=0.0)
    y_int = tf['y_int']
    action_net_r = tf['action_net_r']
    timestamps = tf['timestamps']
    print('  %d features, %d samples (%.1fs)' % (X.shape[1], X.shape[0], time.time()-t0))

    n = X.shape[0]
    fold_size = n // 7
    purge = max(fold_size // 4, 12)
    embargo = max(fold_size // 8, 12)

    # fc997b4 harness: train GBoostTrainer per fold, get probas
    print('[2] Purged WFV (6 folds)...')
    t0 = time.time()
    all_preds, all_y, all_proba_3class, all_ts, all_r = [], [], [], [], []

    for k in range(6):
        te = (k + 2) * fold_size
        vs = te + purge + embargo
        ve = min(vs + fold_size, n)
        if ve - vs < 100: continue
        X_tr, y_tr = X[:te], y_int[:te]
        X_val, y_val = X[vs:ve], y_int[vs:ve]

        trainer = XGBoostTrainer(mode=mode)
        result = trainer.train(X_tr, y_tr)
        proba_3class = result.model.inplace_predict(X_val)
        preds = np.argmax(proba_3class, axis=1)

        all_preds.append(preds)
        all_y.append(y_val)
        all_proba_3class.append(proba_3class)
        all_ts.append(timestamps[vs:ve])
        all_r.append(action_net_r[vs:ve])

    preds = np.concatenate(all_preds)
    yv = np.concatenate(all_y)
    proba_3class = np.vstack(all_proba_3class)
    ts_all = np.concatenate(all_ts)
    r_all = np.concatenate(all_r)
    n_days = len(set(ts_all // 86400000))
    print('  OOS: %d samples, %d days (%.0fs)' % (len(preds), n_days, time.time()-t0))

    # A: Baseline (fc997b4 harness)
    print('\n=== A: BASELINE (fc997b4 harness) ===')
    print('Th     N     Daily  Day%%  Win%%    NetR    2xR')
    baseline_results = {}
    for th in [0.30, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
        act = (proba_3class.max(axis=1) > th) & (preds != 2)
        na = int(act.sum())
        if na == 0: continue
        dr = na / max(n_days, 1)
        wr = float(np.mean(preds[act] == yv[act]))
        rm = float(np.mean(r_all[act]))
        baseline_results[th] = (na, dr, wr, rm)
        print('%4.2f %6d %5.1f %5.1f%% %5.1f%% %7.5f %7.5f' % (th, na, dr, len(set(ts_all[act]//86400000))/max(n_days,1)*100, wr*100, rm, rm*2))

    # B: Temperature scaling on fc997b4 probas
    for temp_label, temp in [('T0.9', 0.9), ('T0.7', 0.7), ('T0.5', 0.5)]:
        print('\n=== B: %s on fc997b4 probas ===' % temp_label)
        logits = np.log(proba_3class + 1e-10)
        proba_temp = softmax(logits, T=temp)
        preds_temp = np.argmax(proba_temp, axis=1)
        print('Th     N     Daily  Day%%  Win%%    NetR    2xR')
        for th in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
            act = (proba_temp.max(axis=1) > th) & (preds_temp != 2)
            na = int(act.sum())
            if na == 0: continue
            dr = na / max(n_days, 1)
            wr = float(np.mean(preds_temp[act] == yv[act]))
            rm = float(np.mean(r_all[act]))
            print('%4.2f %6d %5.1f %5.1f%% %5.1f%% %7.5f %7.5f' % (th, na, dr, len(set(ts_all[act]//86400000))/max(n_days,1)*100, wr*100, rm, rm*2))

    # C: Feature pruning on fc997b4
    print('\n=== C: Top50 features only (fc997b4 harness) ===')
    all_preds_p, all_y_p, all_proba_p, all_ts_p, all_r_p = [], [], [], [], []
    for k in range(6):
        te = (k + 2) * fold_size
        vs = te + purge + embargo
        ve = min(vs + fold_size, n)
        if ve - vs < 100: continue
        X_tr, y_tr = X[:te], y_int[:te]
        X_val, y_val = X[vs:ve], y_int[vs:ve]

        # Select top 50 features by importance
        pre = XGBClassifier(n_estimators=50, max_depth=4, random_state=42, verbosity=0)
        pre.fit(X_tr, y_tr)
        top_idx = np.argsort(pre.feature_importances_)[-50:]
        X_tr_use, X_val_use = X_tr[:, top_idx], X_val[:, top_idx]

        trainer = XGBoostTrainer(mode=mode)
        result = trainer.train(X_tr_use, y_tr)
        proba_p = result.model.inplace_predict(X_val_use)
        preds_p = np.argmax(proba_p, axis=1)

        all_preds_p.append(preds_p)
        all_y_p.append(y_val)
        all_proba_p.append(proba_p)
        all_ts_p.append(timestamps[vs:ve])
        all_r_p.append(action_net_r[vs:ve])

    preds_p = np.concatenate(all_preds_p)
    yv_p = np.concatenate(all_y_p)
    proba_p = np.vstack(all_proba_p)
    ts_all_p = np.concatenate(all_ts_p)
    r_all_p = np.concatenate(all_r_p)
    n_days_p = len(set(ts_all_p // 86400000))

    print('Th     N     Daily  Day%%  Win%%    NetR    2xR')
    for th in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
        act = (proba_p.max(axis=1) > th) & (preds_p != 2)
        na = int(act.sum())
        if na == 0: continue
        dr = na / max(n_days_p, 1)
        wr = float(np.mean(preds_p[act] == yv_p[act]))
        rm = float(np.mean(r_all_p[act]))
        print('%4.2f %6d %5.1f %5.1f%% %5.1f%% %7.5f %7.5f' % (th, na, dr, len(set(ts_all_p[act]//86400000))/max(n_days_p,1)*100, wr*100, rm, rm*2))

    # Summary
    print('\n' + '='*60)
    print('SUMMARY (fc997b4 harness, cost-honest, real timestamps)')
    print('='*60)
    print('NetR >= 0.02 AND N >= 200 check:')
    for th in [0.50, 0.55, 0.60, 0.65]:
        if th in baseline_results:
            na, dr, wr, rm = baseline_results[th]
            meets = 'YES' if (rm >= 0.02 and na >= 200) else 'NO'
            print('  Baseline th=%.2f: N=%d, Win=%.1f%%, NetR=%.5f --> %s' % (th, na, wr*100, rm, meets))

if __name__ == '__main__':
    run()
