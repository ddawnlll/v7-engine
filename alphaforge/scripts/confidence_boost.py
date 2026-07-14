"""Confidence boost: temperature scaling + feature pruning."""
import numpy as np, pandas as pd, sys
sys.path.insert(0, "alphaforge/src")
from xgboost import XGBClassifier

PANEL = "/root/v7-engine/cache/v7_lite_expanded_panel_v1"
TOP10 = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT","LINKUSDT","DOTUSDT"]

def softmax(logits, T=1.0):
    x = logits / T; x -= np.max(x, axis=1, keepdims=True)
    e = np.exp(x); return e / e.sum(axis=1, keepdims=True)

def make_labels(close, n):
    y = np.zeros(n, dtype=np.int32); r = np.zeros(n, dtype=np.float64)
    for i in range(12, n - 1):
        fwd = close[i+1]/close[i]-1
        if fwd > 0.001: y[i]=0; r[i]=fwd
        elif fwd < -0.001: y[i]=1; r[i]=fwd
    return y, r

def run():
    from alphaforge.features.pipeline import compute_features
    close_df = pd.read_parquet(PANEL+"/panel_v7lite_expanded_close.parquet")
    ohlcv_raw = {}
    for f in ["close","high","low","open","volume"]:
        ohlcv_raw[f] = pd.read_parquet(PANEL+"/panel_v7lite_expanded_"+f+".parquet")[f].values.astype(np.float64)
    ohlcv_raw["symbol"] = close_df["symbol"].values

    all_X, all_y, all_r = [], [], []
    for sym in TOP10:
        mask = ohlcv_raw["symbol"] == sym
        ohlcv_sym = {k: v[mask] for k, v in ohlcv_raw.items() if k != "symbol"}
        n = len(ohlcv_sym["close"])
        if n < 5000: continue
        fm = compute_features(ohlcv_sym, mode="SCALP")
        X = np.column_stack([fm.features[k] for k in fm.features.keys()])
        X = np.nan_to_num(X, nan=0.0)
        y, r = make_labels(ohlcv_sym["close"], n)
        all_X.append(X[-n:]); all_y.append(y[-n:]); all_r.append(r[-n:])

    mx = max(x.shape[1] for x in all_X)
    for i in range(len(all_X)):
        if all_X[i].shape[1] < mx:
            all_X[i] = np.hstack([all_X[i], np.zeros((all_X[i].shape[0], mx-all_X[i].shape[1]))])

    X_all = np.vstack(all_X); y_all = np.concatenate(all_y); r_all = np.concatenate(all_r)
    n = len(y_all); fs, pu, em = n//4, n//16, n//32

    def wfv(Xd, yd, temp=1.0, topk=None):
        p, y, pm = [], [], []
        for k in range(3):
            te = (k+1)*fs; vs = te+pu; ve = min(vs+fs, n)
            if ve-vs < 100: continue
            Xtr, Xv = Xd[:te], Xd[vs:ve]; yt, yv = yd[:te], yd[vs:ve]
            Xu = Xtr; Xvu = Xv
            if topk and topk < Xtr.shape[1]:
                pre = XGBClassifier(n_estimators=50, max_depth=4, random_state=42, verbosity=0)
                pre.fit(Xtr, yt)
                idx = np.argsort(pre.feature_importances_)[-topk:]
                Xu, Xvu = Xtr[:, idx], Xv[:, idx]
            clf = XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.05,
                                objective="multi:softprob", num_class=3, random_state=42, verbosity=0, subsample=0.8)
            clf.fit(Xu, yt, verbose=False)
            proba = clf.predict_proba(Xvu)
            if temp != 1.0:
                logits = np.log(proba + 1e-10); proba = softmax(logits, T=temp)
            p.append(np.argmax(proba, axis=1)); y.append(yv); pm.append(np.max(proba, axis=1))
        return np.concatenate(p), np.concatenate(y), np.concatenate(pm)

    exps = [("Baseline", 1.0, None), ("Temp=0.7", 0.7, None), ("Temp=0.5", 0.5, None),
            ("Top50", 1.0, 50), ("Top50+T0.7", 0.7, 50), ("Top50+T0.5", 0.5, 50),
            ("Top30+T0.7", 0.7, 30), ("Top30+T0.5", 0.5, 30)]

    for tl, th in [("th=0.65", 0.65), ("th=0.70", 0.70)]:
        print("\n=== %s ===" % tl)
        print("%-15s %6s %5s %9s" % ("Exp","N","Win%","NetR")); print("-"*40)
        for nm, tmp, tk in exps:
            pr, yv, pm = wfv(X_all, y_all, temp=tmp, topk=tk)
            act = (pm > th) & (pr != 2); na = int(act.sum())
            if na == 0: print("%-15s %6s %5s %9s" % (nm,"0","-","-")); continue
            wr = float(np.mean(pr[act]==yv[act])); rm = float(np.mean(r_all[-len(pr):][act]))
            print("%-15s %6d %5.1f%% %9.6f" % (nm, na, wr*100, rm))

if __name__ == "__main__": run()
