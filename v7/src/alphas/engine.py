"""Walk-forward backtest engine for hypothesis testing."""

import logging
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import (
    N_FOLDS, TRAIN_WINDOW_MONTHS, BOOTSTRAP_SAMPLES,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT,
    START_DATE, END_DATE, OOS_START,
    REALISTIC_COST_MODEL, BLOCKED_REGIMES,
    MAKER_FEE, TAKER_FEE, SLIPPAGE_TIER1, SLIPPAGE_TIER2, SLIPPAGE_TIER3,
    ESTIMATED_TIER_1, ESTIMATED_TIER_2,
)
from .utils import (
    generate_folds, compute_r_multiple, bootstrap_r_multiples,
    save_csv, save_json, save_text, label_regime_for_df,
    save_hypothesis_results, load_hypothesis_results,
)

logger = logging.getLogger(__name__)


class WalkForwardEngine:
    """Walk-forward backtesting engine.

    Manages fold generation, train/test splits, and result aggregation.
    """

    def __init__(
        self,
        hypothesis_name: str,
        signal_fn: Callable,
        param_grid: Optional[List[dict]] = None,
        max_hold_hours: int = 24,
        stop_pct: float = STOP_LOSS_PCT,
        tp_pct: float = TAKE_PROFIT_PCT,
    ):
        self.hypothesis_name = hypothesis_name
        self.signal_fn = signal_fn
        self.param_grid = param_grid or [{}]
        self.max_hold_hours = max_hold_hours
        self.stop_pct = stop_pct
        self.tp_pct = tp_pct

        self.folds = generate_folds(
            start_date=START_DATE,
            end_date=END_DATE,
            n_folds=N_FOLDS,
            train_months=TRAIN_WINDOW_MONTHS,
            oos_start=OOS_START,
        )

        self.all_trades: List[dict] = []
        self.fold_results: List[dict] = []

    def run(self, data: Dict[str, pd.DataFrame]) -> Dict:
        """Run walk-forward validation over all folds.

        Checks cache first — if results exist from a previous run,
        they are loaded instantly instead of re-executing.

        data: dict of symbol -> DataFrame with OHLCV data (frequency = 1h).
        """
        # Check cache
        cached = load_hypothesis_results(self.hypothesis_name)
        if cached is not None:
            logger.info(f"⚡ Loaded cached results for {self.hypothesis_name}")
            self.all_trades = cached.get("_trades", [])
            self.fold_results = cached.get("fold_results", [])
            return cached

        self.all_trades = []
        self.fold_results = []

        logger.info(f"▶ Running {self.hypothesis_name}: {len(self.folds)} folds")

        for fold in self.folds:
            fold_id = fold["fold_id"]
            train_start, train_end = fold["train_start"], fold["train_end"]
            test_start, test_end = fold["test_start"], fold["test_end"]

            logger.info(f"  Fold {fold_id}: train {train_start}-{train_end}, "
                        f"test {test_start}-{test_end}")

            # ── Parameter selection on train window ──
            best_params, best_metric = self._select_params(data, train_start, train_end)

            # ── Test on out-of-sample window ──
            trades = self._run_on_window(
                data, test_start, test_end, best_params, fold_id
            )

            r_vals = [t["r_multiple"] for t in trades]
            median_r = float(np.median(r_vals)) if r_vals else 0.0
            mean_r = float(np.mean(r_vals)) if r_vals else 0.0

            # Bootstrap
            boot = bootstrap_r_multiples(r_vals, BOOTSTRAP_SAMPLES)
            boot_median = float(np.median(boot))
            boot_std = float(np.std(boot))

            fold_result = {
                "fold_id": fold_id,
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
                "num_signals": len(trades),
                "median_r_multiple": median_r,
                "mean_r_multiple": mean_r,
                "bootstrap_median_r": boot_median,
                "bootstrap_std_r": boot_std,
                "best_params": best_params,
            }
            self.fold_results.append(fold_result)
            self.all_trades.extend(trades)

            logger.info(f"    -> {len(trades)} signals, median R={median_r:.3f}")

        results = self._aggregate_results()
        results["_trades"] = self.all_trades
        save_hypothesis_results(self.hypothesis_name, results)
        logger.info(f"📦 Cached results for quick reload on next run")
        return results

    def _select_params(
        self,
        data: Dict[str, pd.DataFrame],
        train_start: str,
        train_end: str,
    ) -> Tuple[dict, float]:
        """Select best parameters on training window using median R-multiple.

        Falls back to the first param set if no trades are generated (e.g.
        the training window has no signals).
        """
        best_params = self.param_grid[0] if self.param_grid else {}
        best_metric = -999.0

        for params in self.param_grid:
            trades = self._run_on_window(
                data, train_start, train_end, params, fold_id=0, is_train=True
            )
            r_vals = [t["r_multiple"] for t in trades]
            metric = float(np.median(r_vals)) if r_vals else -999.0
            if metric > best_metric:
                best_metric = metric
                best_params = params

        return best_params, best_metric

    def _run_on_window(
        self,
        data: Dict[str, pd.DataFrame],
        start: str,
        end: str,
        params: dict,
        fold_id: int,
        is_train: bool = False,
    ) -> List[dict]:
        """Run signal function on a specific time window."""
        trades = []
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)

        for symbol, df in data.items():
            if df.empty:
                continue
            mask = (df["timestamp"] >= start_ts) & (df["timestamp"] < end_ts)
            window = df[mask].copy()
            if len(window) < 10:
                continue

            # Add regime labels
            window = label_regime_for_df(window)

            # Generate signals
            signals = self.signal_fn(window, symbol, params)

            for sig in signals:
                # ── Regime filter: skip signals in blocked regimes ──
                entry_idx = sig["entry_idx"]
                if 0 <= entry_idx < len(window):
                    regime = window.iloc[entry_idx].get("regime", "RANGE")
                    if regime in BLOCKED_REGIMES:
                        continue

                trade = self._simulate_trade(sig, window, symbol, fold_id, is_train)
                if trade:
                    trades.append(trade)

        return trades

    def _get_volume_rank(self, symbol: str) -> int:
        """Estimate volume rank for slippage tier."""
        if symbol in ESTIMATED_TIER_1:
            return 5   # top decile
        elif symbol in ESTIMATED_TIER_2:
            return 25  # 2nd-3rd decile
        else:
            return 50  # bottom half

    def _apply_costs(self, price: float, direction: int, symbol: str,
                     is_entry: bool) -> float:
        """Apply realistic commission + slippage to a price.

        Returns the effective fill price after costs.
        """
        if not REALISTIC_COST_MODEL:
            return price

        rank = self._get_volume_rank(symbol)
        if rank <= 10:
            slip = SLIPPAGE_TIER1
        elif rank <= 40:
            slip = SLIPPAGE_TIER2
        else:
            slip = SLIPPAGE_TIER3

        fee = TAKER_FEE  # assume taker for all entries
        total_cost = fee + slip

        if is_entry:
            if direction == 1:  # long pays ask
                return price * (1 + total_cost)
            else:  # short sells bid
                return price * (1 - total_cost)
        else:
            if direction == 1:  # long sells bid
                return price * (1 - total_cost)
            else:  # short buys ask
                return price * (1 + total_cost)

    def _simulate_trade(
        self,
        signal: dict,
        df: pd.DataFrame,
        symbol: str,
        fold_id: int,
        is_train: bool,
    ) -> Optional[dict]:
        """Simulate a single trade from signal to exit.

        Applies realistic costs (fee + slippage) when REALISTIC_COST_MODEL
        is enabled in config.
        """
        entry_idx = signal["entry_idx"]
        direction = signal["direction"]

        if entry_idx < 0 or entry_idx >= len(df):
            return None

        entry_row = df.iloc[entry_idx]
        raw_entry_price = entry_row["close"]
        entry_price = self._apply_costs(raw_entry_price, direction, symbol, is_entry=True)
        entry_time = entry_row["timestamp"]

        freq_h = self._infer_freq(df)
        max_hold = max(1, int(self.max_hold_hours / freq_h) if freq_h > 0 else 1)

        exit_idx = entry_idx
        exit_price = entry_price
        exit_time = entry_time
        hit_stop = False
        hit_tp = False

        for i in range(entry_idx + 1, min(entry_idx + max_hold + 1, len(df))):
            bar = df.iloc[i]
            high, low = bar["high"], bar["low"]

            if direction == 1:  # long
                stop_price = raw_entry_price * (1 - self.stop_pct)
                if low <= stop_price:
                    exit_price = self._apply_costs(stop_price, direction, symbol, is_entry=False)
                    exit_time = bar["timestamp"]
                    hit_stop = True
                    exit_idx = i
                    break
                tp_price = raw_entry_price * (1 + self.tp_pct)
                if high >= tp_price:
                    exit_price = self._apply_costs(tp_price, direction, symbol, is_entry=False)
                    exit_time = bar["timestamp"]
                    hit_tp = True
                    exit_idx = i
                    break
            else:  # short
                stop_price = raw_entry_price * (1 + self.stop_pct)
                if high >= stop_price:
                    exit_price = self._apply_costs(stop_price, direction, symbol, is_entry=False)
                    exit_time = bar["timestamp"]
                    hit_stop = True
                    exit_idx = i
                    break
                tp_price = raw_entry_price * (1 - self.tp_pct)
                if low <= tp_price:
                    exit_price = self._apply_costs(tp_price, direction, symbol, is_entry=False)
                    exit_time = bar["timestamp"]
                    hit_tp = True
                    exit_idx = i
                    break

            if i == entry_idx + max_hold:
                raw_exit = bar["close"]
                exit_price = self._apply_costs(raw_exit, direction, symbol, is_entry=False)
                exit_time = bar["timestamp"]
                exit_idx = i
                break
        else:
            raw_exit = df.iloc[-1]["close"]
            exit_price = self._apply_costs(raw_exit, direction, symbol, is_entry=False)
            exit_time = df.iloc[-1]["timestamp"]

        r_multiple = compute_r_multiple(
            raw_entry_price, exit_price, direction,
            stop_pct=self.stop_pct, take_profit_pct=self.tp_pct,
        )

        hold_hours = (exit_time - entry_time).total_seconds() / 3600
        regime = entry_row.get("regime", "UNKNOWN")

        return {
            "timestamp": str(entry_time),
            "symbol": symbol,
            "signal_direction": direction,
            "entry_price": round(entry_price, 8),
            "exit_price": round(exit_price, 8),
            "r_multiple": round(r_multiple, 4),
            "hold_duration_hours": round(hold_hours, 2),
            "regime": regime,
            "fold_id": fold_id,
            "is_train": is_train,
            "hit_stop": hit_stop,
            "hit_tp": hit_tp,
            "cost_model_applied": REALISTIC_COST_MODEL,
        }

    def _infer_freq(self, df: pd.DataFrame) -> float:
        """Infer frequency in hours from the DataFrame."""
        if len(df) < 2:
            return 1.0
        delta = (df["timestamp"].iloc[1] - df["timestamp"].iloc[0]).total_seconds() / 3600
        return max(delta, 1.0)

    def _aggregate_results(self) -> dict:
        """Aggregate results across all folds."""
        trades_df = pd.DataFrame(self.all_trades)

        if trades_df.empty:
            return {
                "total_signals": 0,
                "median_r_multiple": 0.0,
                "mean_r_multiple": 0.0,
                "std_r_multiple": 0.0,
                "win_rate": 0.0,
                "avg_hold_hours": 0.0,
                "regime_breakdown": {},
                "fold_results": self.fold_results,
            }

        r_vals = trades_df["r_multiple"].values
        regime_breakdown = {}
        for regime, group in trades_df.groupby("regime"):
            regime_breakdown[str(regime)] = {
                "count": len(group),
                "median_r": float(np.median(group["r_multiple"])),
                "mean_r": float(np.mean(group["r_multiple"])),
                "win_rate": float((group["r_multiple"] > 0).mean()),
            }

        stats = {
            "total_signals": len(trades_df),
            "median_r_multiple": float(np.median(r_vals)),
            "mean_r_multiple": float(np.mean(r_vals)),
            "std_r_multiple": float(np.std(r_vals)),
            "win_rate": float((r_vals > 0).mean()),
            "avg_hold_hours": float(trades_df["hold_duration_hours"].mean()),
            "regime_breakdown": regime_breakdown,
            "fold_results": self.fold_results,
        }
        return stats


def run_baselines(
    data: Dict[str, pd.DataFrame],
    hypothesis_name: str,
    n_random: int = 1000,
) -> Dict:
    """Run baseline comparisons.

    Returns dict with random, momentum, buy_hold R-multiples.
    Currently returns placeholder values — real baselines require
    the same fold structure and signal generation.
    """
    # For a full implementation, we would:
    # 1. Random: generate random entries at same frequency as hypothesis signals
    # 2. Momentum: enter when price moves > X%
    # 3. Buy-and-hold: hold BTC

    # Placeholder structure:
    baselines = {
        "random_baseline_r": 0.0,
        "momentum_baseline_r": 0.0,
        "buy_hold_r": 0.0,
        "hypothesis_r": 0.0,
    }
    return baselines
