sep = "=" * 50
"""
End-to-end leverage training: loads real-ish data, generates simulation labels,
trains direction + leverage model, evaluates.
"""
import sys, os, numpy as np, json
sys.path.insert(0, "alphaforge/src")
from alphaforge.labels.simulation_labels import generate_leverage_labels
from simulation.engine.margin import ACTION_ID_TO_LABEL, ACTION_ID_TO_DIRECTION_LEVERAGE

# ── 1. Generate synthetic data (replaces data loading) ──
np.random.seed(42)
n = 600
ts = np.arange(n) * 3600000 + 1700000000000

# Uptrend with noise
trend = np.linspace(0, 2000, n)
close = 50000 + trend + np.random.randn(n).cumsum() * 80
high = close + np.abs(np.random.randn(n) * 40)
low = close - np.abs(np.random.randn(n) * 40)

data = {
    "open": close - np.random.randn(n) * 15,
    "high": high, "low": low, "close": close,
    "volume": np.ones(n) * 100 + np.random.randn(n) * 10,
    "timestamp": ts,
    "symbol": np.array(["BTCUSDT"] * 450 + ["ETHUSDT"] * 150),
}

# ── 2. Generate simulation labels ──
print("[1] Generating simulation labels...")
labels = generate_leverage_labels(data, "SCALP", future_bars=10)
print(f"    {len(labels)} labels generated")

# Build aligned feature-label matrix
from alphaforge.train import _get_training_config, MODE_CONFIG
cfg = _get_training_config("SCALP")

# Simple feature engineering: price-based features
close_arr = data["close"]
high_arr = data["high"]
low_arr = data["low"]
symbols_arr = data["symbol"]

all_features = []
all_directions = []
all_leverages = []
all_timestamps = []
all_symbols = []
all_base_net_R = []

for l in labels:
    # Find index of this timestamp in data
    idx = np.where(data["timestamp"] == l.timestamp_ms)[0]
    if len(idx) == 0:
        continue
    i = idx[0]
    if i < 20:  # need lookback
        continue
    
    # Features: returns, volatility, ATR-like
    ret_1 = (close_arr[i] / close_arr[i-1] - 1) if close_arr[i-1] > 0 else 0
    ret_5 = (close_arr[i] / close_arr[i-5] - 1) if close_arr[i-5] > 0 else 0
    ret_10 = (close_arr[i] / close_arr[i-10] - 1) if close_arr[i-10] > 0 else 0
    vol_10 = float(np.std(close_arr[i-10:i] / close_arr[i-11:i-1] - 1)) if i >= 10 else 0
    high_low = (high_arr[i] - low_arr[i]) / close_arr[i] if close_arr[i] > 0 else 0
    bb_position = (close_arr[i] - np.mean(close_arr[i-20:i])) / max(np.std(close_arr[i-20:i]), 1e-10) if i >= 20 else 0
    
    all_features.append([ret_1, ret_5, ret_10, vol_10, high_low, bb_position])
    all_directions.append(l.direction)
    all_leverages.append(l.optimal_leverage)
    all_timestamps.append(l.timestamp_ms)
    all_symbols.append(l.symbol)
    all_base_net_R.append(l.base_net_R)

X = np.array(all_features, dtype=np.float32)
y_dir = np.array(all_directions, dtype=np.int32)
y_lev = np.array(all_leverages, dtype=np.int32)
base_r = np.array(all_base_net_R, dtype=np.float32)

print(f"    Features: {X.shape}")
print(f"    Direction distribution: {np.bincount(y_dir)}")
print(f"    Leverage distribution: {np.bincount(y_lev)}")
print(f"    Positive base_R: {np.sum(base_r > 0)}/{len(base_r)}")

# ── 3. Walk-forward split and train ──
from xgboost import XGBClassifier, XGBRegressor

n_total = len(X)
n_train = int(n_total * 0.7)
X_train, X_val = X[:n_train], X[n_train:]
y_dir_train, y_dir_val = y_dir[:n_train], y_dir[n_train:]
y_lev_train, y_lev_val = y_lev[:n_train], y_lev[n_train:]
base_r_train = base_r[:n_train]

# Train direction classifier
print("\n[2] Training direction classifier...")
clf = XGBClassifier(n_estimators=50, max_depth=4, objective="multi:softprob",
                    num_class=3, random_state=42, eval_metric="mlogloss")
clf.fit(X_train, y_dir_train, 
        eval_set=[(X_val, y_dir_val)],
        verbose=False)

# Evaluate
pred_dir = clf.predict(X_val)
dir_acc = np.mean(pred_dir == y_dir_val)
print(f"    Direction accuracy: {dir_acc:.4f} ({np.sum(pred_dir == y_dir_val)}/{len(y_dir_val)})")

# Confusion matrix
print("    Confusion matrix:")
for true in range(3):
    mask = y_dir_val == true
    if mask.sum() > 0:
        pred_counts = np.bincount(pred_dir[mask], minlength=3)
        print(f"      True {["LONG","SHORT","NO_TRADE"][true]}: {pred_counts}")

# Train leverage regressor (only on active trades with positive base_R)
print("\n[3] Training leverage regressor...")
active_mask = (y_dir_train != 2) & (base_r_train > 0)
if active_mask.sum() > 10:
    reg = XGBRegressor(n_estimators=50, max_depth=3, random_state=42)
    reg.fit(X_train[active_mask], y_lev_train[active_mask])

    # Evaluate on val
    val_active = (y_dir_val != 2)  # use predicted direction active set
    if val_active.sum() > 0:
        pred_lev = reg.predict(X_val[val_active])
        true_lev = y_lev_val[val_active]
        mae = np.mean(np.abs(pred_lev - true_lev))
        rmse = np.sqrt(np.mean((pred_lev - true_lev)**2))
        print(f"    Leverage regressor: MAE={mae:.3f}, RMSE={rmse:.3f}")
        print(f"    Predictions: {pred_lev[:10].round(1)}")
        print(f"    True:        {true_lev[:10]}")
else:
    print("    Skipping: too few active training samples")

# ── 4. Combined evaluation ──
print(f"\n{sep}")
print(f"  LEVERAGE TRAINING RESULTS")
print(f"{sep}")
print(f"  Direction accuracy:     {dir_acc:.4f}")
print(f"  Samples (train/val):    {n_train}/{len(X_val)}")
print(f"  NO_TRADE rate (val):    {np.sum(y_dir_val == 2)/len(y_dir_val):.3f}")
print(f"  Active trade rate:      {np.sum(y_dir_val != 2)/len(y_dir_val):.3f}")

# Expected return: direction accuracy × average base_R of active trades
val_active_r = base_r[n_train:][y_dir_val != 2]
if len(val_active_r) > 0:
    avg_edge = np.mean(val_active_r)
    print(f"  Avg base_R (active):   {avg_edge:.4f}")
    # Expected R = P(correct) * avg_edge - P(wrong) * avg_loss
    correct_mask = pred_dir == y_dir_val
    if np.sum(correct_mask & (y_dir_val != 2)) > 0:
        correct_edge = np.mean(base_r[n_train:][correct_mask & (y_dir_val != 2)])
        wrong_mask = (~correct_mask) & (y_dir_val != 2)
        wrong_edge = np.mean(np.abs(base_r[n_train:][wrong_mask])) if wrong_mask.sum() > 0 else avg_edge
        exp_r = (dir_acc * correct_edge - (1 - dir_acc) * wrong_edge)
        print(f"  Expected R (approx):   {exp_r:.4f}")

print(f"{sep}\n")
