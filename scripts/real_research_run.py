#!/usr/bin/env python3
"""Real data research training run — 10 symbols, Binance OHLCV."""
import numpy as np, pandas as pd, json, os, time, warnings, glob
warnings.filterwarnings('ignore')

print("=" * 60)
print("V7 ENGINE — REAL DATA RESEARCH TRAINING RUN")
print("=" * 60)

# ── 1. Load real data ──
print("\n[1] Loading Binance OHLCV...")
files = glob.glob("data/raw/*/*.parquet")
print(f"  Files: {len(files)}")
all_data = []
for f in sorted(files):
    symbol = f.split("/")[2]
    df = pd.read_parquet(f)
    df["symbol"] = symbol
    all_data.append(df)
data = pd.concat(all_data, ignore_index=True).sort_values(["symbol", "timestamp"])
symbols = data["symbol"].unique().tolist()
print(f"  Symbols ({len(symbols)}): {symbols}")
print(f"  Rows: {len(data)}")

# ── 2. Compute features ──
print("\n[2] Computing features...")
X_parts, y_parts = [], []
for symbol in symbols:
    s = data[data["symbol"] == symbol].copy()
    o, h, l, c, v = s["open"].values, s["high"].values, s["low"].values, s["close"].values, s["volume"].values
    n = len(c)
    ret = np.diff(c, prepend=c[0]); ret[0] = 0
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
    tr[0] = h[0] - l[0]
    atr = np.convolve(tr, np.ones(14)/14, mode="same"); atr[:14] = atr[14]
    ma20 = np.convolve(c, np.ones(20)/20, mode="same")
    ma50 = np.convolve(c, np.ones(50)/50, mode="same")
    vol20 = np.convolve(v, np.ones(20)/20, mode="same")
    feat = np.column_stack([
        ret, np.convolve(ret, np.ones(5)/5, mode="same"),
        np.convolve(ret, np.ones(20)/20, mode="same"),
        c / ma20 - 1, (h - l) / c, v / vol20, atr / c,
        np.maximum(0, ret), np.minimum(0, ret),
        np.convolve(ret > 0, np.ones(10)/10, mode="same"),
        np.convolve(ret, np.ones(3)/3, mode="same") - np.convolve(ret, np.ones(10)/10, mode="same"),
        (c - ma50) / atr, np.abs(c - np.roll(c, 1)) / atr,
        np.convolve(v * (c - np.roll(c, 1)), np.ones(5)/5, mode="same") / vol20,
    ])
    fwd_ret = np.roll(c, -5) / c - 1; fwd_ret[-5:] = 0
    label = np.where(fwd_ret > 0.002, "LONG_NOW", np.where(fwd_ret < -0.002, "SHORT_NOW", "NO_TRADE"))
    X_parts.append(feat); y_parts.append(label)

X = np.vstack(X_parts).astype(np.float64)
y = np.concatenate(y_parts)
valid = ~(np.isnan(X).any(axis=1) | np.isinf(X).any(axis=1))
X, y = X[valid], y[valid]
classes, counts = np.unique(y, return_counts=True)
print(f"  Features: {X.shape[1]} dims, {len(X)} samples")
for c, cnt in zip(classes, counts):
    print(f"    {c}: {cnt} ({cnt/len(y)*100:.1f}%)")

# ── 3. Research profile ──
print("\n[3] Registering research profile...")
from simulation.contracts.models import SimulationProfile, TradingMode
from simulation.profile_registry.registry import register_profile
research = SimulationProfile(profile_version="1.0.0-research", mode=TradingMode.SCALP,
    primary_interval="1h", max_holding_bars=24, stop_multiplier=2.5, target_multiplier=2.5,
    ambiguity_margin_r=0.15, min_action_edge_r=0.10, no_trade_default=True,
    context_intervals=["4h","15m"], refinement_intervals=["15m"],
    stop_method="atr_medium", target_method="atr_medium")
h = register_profile(research)
print(f"  Hash: {h}")

# ── 4. XGBoost training ──
print("\n[4] Training XGBoost (SCALP profile)...")
from alphaforge.training.xgb_trainer import XGBoostTrainer
t0 = time.time()
trainer = XGBoostTrainer(mode="SCALP")
result = trainer.train(X, y)
t1 = time.time()
ma = result.model_artifact
print(f"  Duration: {t1-t0:.2f}s")
print(f"  HP: lr={ma['hyperparameters']['learning_rate']}, depth={ma['hyperparameters']['max_depth']}")
print(f"  Class counts: {dict(ma.get('class_counts',{}))}")
cw = ma.get('class_weights',{})
print(f"  Class weights: NO_TRADE={cw.get(2,0):.2f}, LONG={cw.get(0,0):.2f}, SHORT={cw.get(1,0):.2f}")
print(f"  Val accuracy: {ma['training_metrics']['val_accuracy']:.4f}")
print(f"  Val logloss: {ma['training_metrics']['val_logloss']:.4f}")

# ── 5. IC/RankIC ──
print("\n[5] Signal quality...")
from alphaforge.reports.ic_metrics import compute_ic, compute_rank_ic
probs = result.model.inplace_predict(X)
pred_class = np.argmax(probs, axis=1)
label_map = {"LONG_NOW": 0, "SHORT_NOW": 1, "NO_TRADE": 2}
actual = np.array([label_map[l] for l in y])
directional = probs[:, 0] - probs[:, 1]
directional_actual = np.where(actual == 0, 1.0, np.where(actual == 1, -1.0, 0.0))
ic = compute_ic(directional, directional_actual)
rank_ic = compute_rank_ic(directional, directional_actual)
print(f"  IC={ic:.4f}, RankIC={rank_ic:.4f}")

# ── 6. Per-trade simulation ──
print("\n[6] Simulating trades...")
trades = []
for i in range(0, len(X), 3):
    if actual[i] == 2 or pred_class[i] == 2:
        continue
    side = "LONG" if pred_class[i] == 0 else "SHORT"
    # Directional signal strength as proxy for R
    signal_strength = abs(directional[i])
    trades.append({"side": side, "signal": float(signal_strength), "correct": float(directional[i] * directional_actual[i] > 0)})

if trades:
    correct = sum(1 for t in trades if t["correct"])
    total = len(trades)
    winrate = correct / total
    avg_signal = np.mean([t["signal"] for t in trades])
    print(f"  Directional signals: {total}")
    print(f"  Directional accuracy (winrate): {winrate:.4f} ({correct}/{total})")
    print(f"  Avg signal strength: {avg_signal:.4f}")
    trade_summary = {"n_signals": total, "directional_accuracy": round(float(winrate),4),
        "avg_signal_strength": round(float(avg_signal),6)}
else:
    print("  No trades")
    trade_summary = {"n_signals": 0, "directional_accuracy": 0, "avg_signal_strength": 0}

# ── 7. Save ──
results = {
    "run_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "sha": os.popen("git rev-parse HEAD 2>/dev/null").read().strip(),
    "data": {"symbols": symbols, "bars_per_symbol": 2160, "n_samples": len(X)},
    "training": {
        "duration_s": round(t1-t0, 2),
        "hp_lr": ma['hyperparameters']['learning_rate'],
        "hp_depth": ma['hyperparameters']['max_depth'],
        "val_accuracy": ma['training_metrics']['val_accuracy'],
        "class_counts": {str(k): int(v) for k, v in ma.get('class_counts',{}).items()},
        "class_weights": {str(k): float(v) for k, v in ma.get('class_weights',{}).items()},
    },
    "signal": {"IC": round(float(ic), 6), "RankIC": round(float(rank_ic), 6)},
    "trading": trade_summary,
}
out = "reports/research_run_real_10sym.json"
with open(out, "w") as f:
    json.dump(results, f, indent=2)
print(f"\n✅ Saved: {out}")
print("=" * 60)
