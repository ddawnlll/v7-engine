"""Honest confidence boost: fc997b4 harness WITH CURRENT 56-symbol data."""
import sys, os, time
sys.path.insert(0, "alphaforge/src")
os.chdir("/root/v7-engine-main")

import numpy as np
from xgboost import XGBClassifier
from alphaforge.training.xgb_trainer import XGBoostTrainer
from alphaforge.features.pipeline import compute_features as _cf
import pyarrow.parquet as pq
from pathlib import Path

mode = "SCALP"

# Load ALL 56 symbols
symbols = sorted([d.name for d in Path("data/raw").iterdir() if d.is_dir()])
all_X, all_y, all_r, all_ts = [], [], [], []

for sym in symbols:
    p = Path("data/raw") / sym / f"{sym}_4h.parquet"
    if not p.exists(): continue
    df = pq.read_table(p).to_pandas()
    close = df["close"].values.astype(np.float64)
    high = df["high"].values.astype(np.float64); low = df["low"].values.astype(np.float64)
    vol = df["volume"].values.astype(np.float64); opn = df["open"].values.astype(np.float64)
    ts = df["timestamp"].values if "timestamp" in df.columns else np.arange(len(df))*14400000
    fm = _cf({"close":close,"high":high,"low":low,"volume":vol,"open":opn,"timestamp":ts}, mode=mode)
    ft = np.column_stack([fm.features[k] for k in fm.features])
    from alphaforge.train import _get_training_config
    _cfg = _get_training_config(mode)
    n = len(close); fwd = np.full(n, 0.0, dtype=np.float64)
    for i in range(n - _cfg.label_horizon):
        fwd[i] = (close[i + _cfg.label_horizon] / close[i]) - 1.0
    lbl = np.full(n, 2, dtype=np.int64)
    lbl[fwd > 0.003] = 0; lbl[fwd < -0.003] = 1
    ml = min(len(ft), n)
    all_X.append(np.nan_to_num(ft[:ml], 0))
    all_r.append(fwd[:ml]); all_y.append(lbl[:ml]); all_ts.append(ts[:ml])

X = np.vstack(all_X); r_all = np.concatenate(all_r); y_all = np.concatenate(all_y); ts_all = np.concatenate(all_ts)
print("Panel: %d rows, %d features, %d symbols" % (len(X), X.shape[1], len(symbols)))

# fc997b4 harness WFV
n = len(X); fold_size = n // 7
purge = max(fold_size // 4, 12)
embargo = max(fold_size // 8, 12)

from collections import Counter
unique_days = len(set(ts_all // 86400000))

all_preds, all_yv, all_probas, all_rs = [], [], [], []
for k in range(6):
    te = (k + 2) * fold_size
    vs = te + purge + embargo
    ve = min(vs + fold_size, n)
    if ve - vs < 100: break
    X_tr = X[:te]; y_tr = y_all[:te]
    X_val = X[vs:ve]; y_val = y_all[vs:ve]
    
    trainer = XGBoostTrainer(mode=mode)
    result = trainer.train(X_tr, y_tr)
    proba = result.model.inplace_predict(X_val)
    
    all_preds.append(np.argmax(proba, axis=1))
    all_yv.append(y_val)
    all_probas.append(proba)
    all_rs.append(r_all[vs:ve])

if not all_preds:
    print("No data!"); sys.exit(1)

preds = np.concatenate(all_preds); yv = np.concatenate(all_yv)
probas = np.vstack(all_probas); rv = np.concatenate(all_rs)

n_days = len(set(ts_all // 86400000))
print("\nOOS: %d samples, ~%d days" % (len(preds), n_days))
print("\nBASELINE (honest fc997b4 harness, %d symbols)" % len(symbols))
print("%-8s %-8s %-8s %-8s %-8s" % ("Thresh", "Trades", "Daily", "Win%", "NetR"))
print("-" * 45)

for th in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]:
    conf = np.max(probas, axis=1)
    active = (conf > th) & (preds != 2)
    n_t = int(np.sum(active))
    if n_t == 0: continue
    wr = float(np.mean(preds[active] == yv[active]))
    mr = float(np.mean(rv[active]))
    dr = n_t / n_days
    mark = " <<<" if wr >= 80 and n_t >= 540 else ""
    print("%-8.2f %-8d %-8.1f %-8.1f %+8.4f%s" % (th, n_t, dr, wr*100, mr, mark))
