#!/usr/bin/env python3
"""#211: Central simulation bridge — batch simulation CLI (v0, prepared API).

Loads real SimulationProfile from registry and computes economic metrics
using closed-form approximation (target_r - fee_cost_r, 50% win-rate assumption).
Does NOT call simulation/engine/engine.py simulate() yet.

Future (#???): wire through to engine.simulate() for full path simulation.

Usage:
    python scripts/factor_central_sim.py --mode SCALP --symbols BTCUSDT,ETHUSDT
    python scripts/factor_central_sim.py --input signals.json --output results.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional


def signal_event_to_sim_input(signal: dict, mode: str) -> dict:
    """Convert a signal event dict to simulation input using real profile."""
    from lib.config_training import load_training_config
    cfg = load_training_config(mode)
    return {
        "symbol": signal["symbol"],
        "entry_price": signal.get("entry_price", 100.0),
        "direction": signal.get("direction", "LONG"),
        "stop_multiplier": cfg.stop_multiplier,
        "target_multiplier": cfg.target_multiplier,
        "max_holding_bars": cfg.max_holding_bars,
        "leverage": getattr(cfg, "leverage", 1),
        "atr": signal.get("atr", signal.get("entry_price", 100.0) * 0.01),
    }


def run_batch_simulation(signals: list[dict], mode: str) -> list[dict]:
    """Run batch simulation over a list of signals using real profile config.

    Returns list of result dicts with economic metrics derived from profile.
    """
    from lib.config_training import load_training_config
    cfg = load_training_config(mode)
    results = []
    for sig in signals:
        sim_in = signal_event_to_sim_input(sig, mode)
        # Compute per-signal metrics from real profile parameters
        one_r = sim_in["atr"] * cfg.stop_multiplier
        target_r = cfg.target_multiplier * cfg.stop_multiplier
        fee_cost_r = 0.0008 * sim_in["entry_price"] / one_r if one_r > 0 else 0.0
        results.append({
            "symbol": sim_in["symbol"],
            "direction": sim_in["direction"],
            "entry_price": sim_in["entry_price"],
            "stop_multiplier": cfg.stop_multiplier,
            "target_multiplier": cfg.target_multiplier,
            "one_r": round(one_r, 6),
            "central_net_R": round(target_r - fee_cost_r, 6),
            "central_expectancy_R": round((target_r * 0.5 - 1.0 * 0.5) - fee_cost_r, 6),
            "central_profit_factor": round((target_r * 0.5) / (1.0 * 0.5 + fee_cost_r), 4),
            "central_max_drawdown_R": round(-1.0 - fee_cost_r, 6),
            "leverage": sim_in["leverage"],
        })
    return results


def main():
    parser = argparse.ArgumentParser(description="Central simulation bridge CLI")
    parser.add_argument("--mode", default="SCALP", choices=["SWING", "SCALP", "AGGRESSIVE_SCALP"])
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT")
    parser.add_argument("--input", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            signals = json.load(f)
    else:
        symbols = [s.strip() for s in args.symbols.split(",")]
        signals = [{"symbol": s} for s in symbols]

    results = run_batch_simulation(signals, args.mode)
    output = {"mode": args.mode, "n_signals": len(signals), "results": results}
    text = json.dumps(output, indent=2)
    if args.output:
        Path(args.output).write_text(text)
        print(f"Results saved to {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
