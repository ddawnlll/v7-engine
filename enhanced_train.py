import sys, numpy as np, pandas as pd, time
from xgboost import XGBClassifier
sys.path.insert(0, "alphaforge/src")

panel_dir = "/root/v7-engine/cache/v7_lite_expanded_panel_v1"
close_df = pd.read_parquet(f"{panel_dir}/panel_v7lite_expanded_close.parquet")
ohlcv = {}
for f in ["close","high","low","open","volume"]:
    ohlcv[f] = pd.read_parquet(f"{panel_dir}/panel_v7lite_expanded_{f}.parquet")[f].values.astype(np.float64)
ohlcv["symbol"] = close_df["symbol"].values
ohlcv["timestamp"] = close_df["timestamp"].values.astype(np.int64)

from collections import Counter
sym_lens = Counter()
for sym in set(ohlcv["symbol"]):
    mask = ohlcv["symbol"] == sym
    sym_lens[int(mask.sum())] += 1
target_len = max(sym_lens.keys(), key=lambda k: sym_lens[k])

multi_ohlcv = {}
for sym in set(ohlcv["symbol"]):
    mask = ohlcv["symbol"] == sym
    if int(mask.sum()) != target_len:
        continue
    multi_ohlcv[sym] = {
        "open": ohlcv["open"][mask], "close": ohlcv["close"][mask],
        "high": ohlcv["high"][mask], "low": ohlcv["low"][mask],
        "volume": ohlcv["volume"][mask],
    }
print(f"Multi-symbol: {len(multi_ohlcv)} symbols, {target_len} bars each")

from alphaforge.features.pipeline import compute_features
from alphaforge.features.cross_sectional_rank import compute_cross_sectional_rank_group
from alphaforge.features.lead_lag import compute_lead_lag_group

print("Computing cross-sectional rank features...")
cs_features = compute_cross_sectional_rank_group(multi_ohlcv)
print(f"  {len(cs_features)} CS features computed")

all_X, all_y, all_r, all_ts = [], [], [], []
symbols_list = sorted(multi_ohlcv.keys())
context_sym = "BTCUSDT" if "BTCUSDT" in multi_ohlcv else symbols_list[0]

for sym_idx, sym in enumerate(symbols_list):
    ohlcv_sym = multi_ohlcv[sym]
    feat_matrix = compute_features(ohlcv_sym, mode="SCALP")
    X_base = feat_matrix.matrix
    n_bars = X_base.shape[0]
    cs_cols = []
    for fname, fmat in cs_features.items():
        cs_cols.append(fmat[sym_idx, :n_bars].reshape(-1, 1))
    if sym != context_sym:
        try:
            ll = compute_lead_lag_group(multi_ohlcv=multi_ohlcv, primary_symbol=sym, context_symbol=context_sym)
            for fname, farr in ll.items():
                cs_cols.append(farr[:n_bars].reshape(-1, 1))
        except:
            pass
    X_aug = np.hstack([X_base] + cs_cols)
    X_aug = np.nan_to_num(X_aug, nan=0.0)
    close = ohlcv_sym["close"]
    y = np.zeros(n_bars, dtype=np.int32)
    r = np.zeros(n_bars, dtype=np.float64)
    for i in range(12, n_bars - 1):
        fwd = close[i+1]/close[i]-1
        if fwd > 0.001: y[i]=0; r[i]=fwd
        elif fwd < -0.001: y[i]=1; r[i]=fwd
        else: y[i]=2; r[i]=0.0
    all_X.append(X_aug); all_y.append(y); all_r.append(r); all_ts.append(np.arange(n_bars, dtype=np.int64))
    if (sym_idx+1)%5==0: print(f"  {sym_idx+1}/{len(symbols_list)} done, features={X_aug.shape[1]}")

X_all=np.vstack(all_X); y_all=np.concatenate(all_y); r_all=np.concatenate(all_r); ts_all=np.concatenate(all_ts)
print(f"\nTotal: {X_all.shape[0]} samples, {X_all.shape[1]} features")

n=len(X_all); fold_size=n//7; purge=fold_size//4; embargo=fold_size//8
all_p,all_yv,all_pm=[],[],[]
for k in range(6):
    te=(k+2)*fold_size; vs=te+purge+embargo; ve=min(vs+fold_size,n)
    if ve-vs<100: continue
    X_tr,y_tr=X_all[:te],y_all[:te]; X_val,y_val=X_all[vs:ve],y_all[vs:ve]
    clf=XGBClassifier(n_estimators=150,max_depth=5,learning_rate=0.05,objective="multi:softprob",num_class=3,random_state=42,verbosity=0,subsample=0.8)
    clf.fit(X_tr,y_tr,verbose=False)
    proba=clf.predict_proba(X_val); preds=np.argmax(proba,axis=1)
    all_p.append(preds); all_yv.append(y_val); all_pm.append(np.max(proba,axis=1))
    print(f"Fold {k+1}: acc={np.mean(preds==y_val):.4f}")

preds=np.concatenate(all_p); yv=np.concatenate(all_yv); pm=np.concatenate(all_pm)
# Get OOS net R for last fold
vs_last=(5+2)*fold_size+purge+embargo; ve_last=min(vs_last+fold_size,n)
r_oos=r_all[vs_last:ve_last]; ts_oos=ts_all[vs_last:ve_last]
nd=len(set(ts_oos//86400000))
print(f"\nOOS: {len(preds)} samples, {nd} days")
print(f"\n{'='*80}")
print(f"  ENHANCED: {X_all.shape[1]} features (base + CS rank + lead-lag)")
print(f"{'='*80}")
for th in [0.50,0.55,0.60,0.65,0.70,0.75]:
    act=(pm>th)&(preds!=2); na=int(act.sum())
    if na==0: continue
    dr=na/max(nd,1); ar=r_oos[:len(pm)][act] if len(r_oos)>=len(pm) else r_oos[:na]
    wr=float(np.mean(preds[act]==yv[act])); rm=float(np.mean(ar)) if len(ar)>0 else 0
    print(f"  th={th:.2f}: N={na} daily={dr:.1f} win={wr*100:.1f}% netR={rm:.6f} 2x={rm*2:.6f} 5x={rm*5:.6f}")
print(f"{'='*80}")
