import sys, numpy as np
sys.path.insert(0, "alphaforge/src")
import pytest
from alphaforge.labels.simulation_labels import generate_leverage_labels

@pytest.fixture(scope="module")
def training_data():
    np.random.seed(42); n = 600
    ts = np.arange(n) * 3600000 + 1700000000000
    trend = np.linspace(0, 2000, n)
    close = 50000 + trend + np.random.randn(n).cumsum() * 80
    high = close + np.abs(np.random.randn(n) * 40)
    low = close - np.abs(np.random.randn(n) * 40)
    return {"open": close - np.random.randn(n) * 15,
        "high": high, "low": low, "close": close,
        "volume": np.ones(n) * 100 + np.random.randn(n) * 10,
        "timestamp": ts,
        "symbol": np.array(["BTCUSDT"] * 450 + ["ETHUSDT"] * 150)}

@pytest.fixture(scope="module")
def sim_labels(training_data):
    return generate_leverage_labels(training_data, "SCALP", future_bars=10)

class TestLeverageE2E:
    def test_label_count(self, sim_labels):
        assert len(sim_labels) > 100

    def test_13_actions(self, sim_labels):
        assert len(sim_labels[0].action_outcomes) == 13

    def test_direction_dist(self, sim_labels):
        d = np.bincount([l.direction for l in sim_labels], minlength=3)
        assert all(c > 0 for c in d)

    def test_invariant(self, sim_labels):
        for l in sim_labels[:20]:
            longs = [v for k,v in l.action_outcomes.items() if v.direction=="LONG" and v.leverage>0]
            if longs:
                assert all(abs(v.base_net_R - longs[0].base_net_R) < 1e-12 for v in longs)

    def test_zero_lev_when_no_edge(self, sim_labels):
        for l in sim_labels[:30]:
            if l.base_net_R <= 0:
                assert l.optimal_leverage == 0

    def test_xgb_direction(self, sim_labels, training_data):
        from xgboost import XGBClassifier
        c = training_data["close"]; h = training_data["high"]; l = training_data["low"]
        X, y = [], []
        for lb in sim_labels:
            idx = np.where(training_data["timestamp"] == lb.timestamp_ms)[0]
            if len(idx)==0 or idx[0]<20: continue
            i = idx[0]
            r1 = (c[i]/c[i-1]-1) if c[i-1]>0 else 0
            r5 = (c[i]/c[i-5]-1) if c[i-5]>0 else 0
            r10 = (c[i]/c[i-10]-1) if c[i-10]>0 else 0
            v10 = float(np.std(c[i-10:i]/c[i-11:i-1]-1)) if i>=10 else 0
            hl = (h[i]-l[i])/c[i] if c[i]>0 else 0
            bb = (c[i]-np.mean(c[i-20:i]))/max(np.std(c[i-20:i]),1e-10) if i>=20 else 0
            X.append([r1,r5,r10,v10,hl,bb]); y.append(lb.direction)
        X=np.array(X); y=np.array(y)
        n70=int(len(X)*0.7)
        clf=XGBClassifier(n_estimators=50,max_depth=4,num_class=3,random_state=42)
        clf.fit(X[:n70],y[:n70],eval_set=[(X[n70:],y[n70:])],verbose=False)
        acc=np.mean(clf.predict(X[n70:])==y[n70:])
        assert acc>0.33, f"acc={acc:.3f}"

    def test_xgb_leverage(self, sim_labels, training_data):
        from xgboost import XGBRegressor
        c = training_data["close"]
        X, y_lev = [], []
        for lb in sim_labels:
            idx = np.where(training_data["timestamp"]==lb.timestamp_ms)[0]
            if len(idx)==0 or idx[0]<20: continue
            i=idx[0]
            r1=(c[i]/c[i-1]-1) if c[i-1]>0 else 0
            r5=(c[i]/c[i-5]-1) if c[i-5]>0 else 0
            r10=(c[i]/c[i-10]-1) if c[i-10]>0 else 0
            X.append([r1,r5,r10]); y_lev.append(lb.optimal_leverage)
        X=np.array(X); y=np.array(y_lev)
        n70=int(len(X)*0.7)
        active=np.where(y[:n70]>0)[0]
        if len(active)>=10:
            reg=XGBRegressor(n_estimators=50,max_depth=3,random_state=42)
            reg.fit(X[:n70][active],y[:n70][active])
            va=np.where(y[n70:]>0)[0]
            if len(va)>0:
                pred=reg.predict(X[n70:][va])
                assert float(np.mean(np.abs(pred-y[n70:][va])))<5.0

if __name__=="__main__":
    pytest.main(["-v","__file__"])
