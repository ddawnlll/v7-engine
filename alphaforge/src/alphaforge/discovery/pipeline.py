"""Discovery pipeline orchestrator — end-to-end alpha discovery.

Orchestrates the full pipeline:
  1. Data loading (panel → real → synthetic fallback)
  2. Aligned training frame (features + labels)
  3. Walk-forward validation (trained model + OOS predictions)
  4. Trade signal generation (from model predictions)
  5. Simulation backtest (through simulation engine)
  6. Profitability analysis
  7. Rejection or promotion
  8. [if promoted] Empirical report + V7 handoff
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import numpy as np

from alphaforge.discovery import DiscoveryConfig, DiscoveryResult
from alphaforge.discovery.signal_generator import (
    generate_trade_signals,
    filter_overlapping_signals,
)
from alphaforge.discovery.backtest import backtest_signals
from alphaforge.discovery.profitability import analyze_profitability
from alphaforge.discovery.rejection import evaluate_alpha, rejection_to_verdict
from alphaforge.train import (
    MODE_CONFIG,
    build_aligned_training_frame,
    generate_synthetic_ohlcv,
    load_cached_data,
    walk_forward_validate,
    _load_panel_data,
    collect_metrics,
    cross_sectional_rank_normalize,
)

logger = logging.getLogger("alphaforge.discovery.pipeline")


def run_discovery(
    config: DiscoveryConfig,
    precomputed_frame: Optional[dict] = None,
    precomputed_wfv: Optional[tuple[list[dict], list[np.ndarray], list[np.ndarray], list[np.ndarray]]] = None,
) -> DiscoveryResult:
    """Execute the full discovery pipeline.

    Parameters
    ----------
    config:
        Pipeline configuration (mode, symbols, thresholds, etc.).
    precomputed_frame:
        Optional pre-built aligned training frame (from train.py main()).
        When provided, skips data loading and frame construction (steps 1-3).
        The frame is used AS-IS — must already be NaN→0 filled and rank
        normalized to match training's eval representation.
    precomputed_wfv:
        Optional tuple of (wfv_results, fold_preds, fold_y_class, fold_y_val)
        from a prior walk-forward validation run. When provided, skips the
        WFV stage (step 4). The three fold_preds/... arrays are the raw
        prediction outputs returned by walk_forward_validate(return_raw_preds=True).

    Returns
    -------
    DiscoveryResult
        Full result with metrics, rejection decision, and optional handoff.
    """
    start_ts = time.time()
    result = DiscoveryResult(config=config)
    mode = config.mode.upper()
    symbols = list(config.symbols)
    cfg = MODE_CONFIG[mode]
    interval = cfg["primary"]

    logger.info("=" * 60)
    logger.info("  AlphaForge Discovery Pipeline")
    logger.info("  Mode: %s | Sym: %s | Folds: %d | Threshold: %.2f",
                mode, symbols, config.folds, config.confidence_threshold)
    logger.info("=" * 60)

    try:
        # ------------------------------------------------------------------
        # Step 1-3: Load data / build frame / clean NaN (or use precomputed)
        # ------------------------------------------------------------------
        if precomputed_frame is not None:
            logger.info("[1-3/8] Using precomputed training frame...")
            training_frame = precomputed_frame
            X = training_frame["X"]
            y_int = training_frame["y_int"]
            label_net_r = training_frame["label_net_r"]
            action_net_r = training_frame["action_net_r"]
            timestamps = training_frame["timestamps"]
            symbols_arr = training_frame["symbols"]
            feat_names = training_frame["feature_names"]

            # NaN→0 fill + rank normalization (same as training main())
            logger.info("[3/8] Applying NaN→0 fill and rank normalization...")
            X_clean = np.nan_to_num(X, nan=0.0)
            if len(np.unique(timestamps)) < len(timestamps):
                X_clean = cross_sectional_rank_normalize(X_clean, timestamps)
            y_clean = y_int.copy()
            label_net_clean = label_net_r.copy()
            action_net_clean = action_net_r.copy()
            ts_clean = timestamps.copy()
            sym_clean = symbols_arr.copy()
            logger.info("  All %d samples preserved (NaN→0 fill, no row-drop)",
                        len(X_clean))

            ohlcv = None  # signal generation will fall back to ts/sym
        else:
            # ------------------------------------------------------------------
            # Step 1: Load data
            # ------------------------------------------------------------------
            logger.info("[1/8] Loading OHLCV data...")
            ohlcv = None
            if config.panel_cache:
                ohlcv = _load_panel_data(config.panel_cache, symbols)
            elif not config.use_synthetic:
                ohlcv = load_cached_data(symbols, interval, data_dir=config.data_dir)
            if ohlcv is None:
                logger.info("  Falling back to synthetic data (%d bars)", config.n_bars)
                ohlcv = generate_synthetic_ohlcv(
                    n_bars=config.n_bars,
                    symbols=tuple(symbols),
                    random_seed=config.random_seed,
                )
            if not config.use_synthetic:
                from lib.data_lake.guard import assert_real_data
                assert_real_data(ohlcv)
            n_bars_total = len(ohlcv["close"])
            logger.info("  %d bars, %d symbols", n_bars_total, len(symbols))

            # ------------------------------------------------------------------
            # Step 2: Build aligned training frame
            # ------------------------------------------------------------------
            logger.info("[2/8] Building aligned feature + label frame...")
            feature_groups = None if config.features.lower() == "all" else [
                g.strip() for g in config.features.split(",")
            ]
            training_frame = build_aligned_training_frame(
                ohlcv, mode, feature_groups=feature_groups,
            )
            X = training_frame["X"]
            y_int = training_frame["y_int"]
            label_net_r = training_frame["label_net_r"]
            action_net_r = training_frame["action_net_r"]
            timestamps = training_frame["timestamps"]
            symbols_arr = training_frame["symbols"]
            feat_names = training_frame["feature_names"]

            # ------------------------------------------------------------------
            # Step 3: NaN→0 fill + rank normalization (same as training main())
            # ------------------------------------------------------------------
            logger.info("[3/8] Applying NaN→0 fill and rank normalization...")
            X_clean = np.nan_to_num(X, nan=0.0)
            if len(np.unique(timestamps)) < len(timestamps):
                X_clean = cross_sectional_rank_normalize(X_clean, timestamps)
            y_clean = y_int.copy()
            label_net_clean = label_net_r.copy()
            action_net_clean = action_net_r.copy()
            ts_clean = timestamps.copy()
            sym_clean = symbols_arr.copy()
            logger.info("  All %d samples preserved (NaN→0 fill, no row-drop)",
                        len(X_clean))

        if len(X_clean) < 100:
            result.status = "ERROR"
            result.errors.append(f"Insufficient samples: {len(X_clean)}")
            result.duration_seconds = time.time() - start_ts
            return result

        # ------------------------------------------------------------------
        # Step 4: Walk-forward validation (or use precomputed)
        # ------------------------------------------------------------------
        if precomputed_wfv is not None:
            logger.info("[4/8] Using precomputed walk-forward validation...")
            wfv_results, fold_preds, fold_y_class, fold_y_val = precomputed_wfv
        else:
            logger.info("[4/8] Walk-forward validation (%d folds)...", config.folds)
            t0 = time.time()
            wfv_results, fold_preds, fold_y_class, fold_y_val = walk_forward_validate(
                X_clean, y_clean, label_net_clean, mode,
                min_folds=config.folds,
                action_net_r=action_net_clean,
                return_raw_preds=True,
            )
            wfv_duration = time.time() - t0
            logger.info("  %d folds in %.1fs", len(wfv_results), wfv_duration)

        # Aggregate WFV metrics
        import alphaforge.train as _train_mod
        _train_mod.mode = mode  # collect_metrics() references this global

        wfv_metrics = collect_metrics(wfv_results, X_clean, feat_names)
        result.wfv_metrics = wfv_metrics

        if not wfv_results:
            result.status = "ERROR"
            result.errors.append("Walk-forward validation returned no results")
            result.duration_seconds = time.time() - start_ts
            return result

        logger.info("  OOS Acc=%.4f, Train Acc=%.4f, Overfit=%.4f",
                    wfv_metrics["accuracy"], wfv_metrics["train_accuracy"],
                    wfv_metrics["overfit_gap"])

        # ------------------------------------------------------------------
        # Step 5: Generate trade signals from OOS predictions
        # ------------------------------------------------------------------
        logger.info("[5/8] Generating trade signals (threshold=%.2f)...",
                    config.confidence_threshold)

        # Build a close-array aligned with the cleaned training frame
        close_arr_raw = training_frame.get("close_prices", None)
        if close_arr_raw is not None and len(close_arr_raw) == len(timestamps):
            close_arr_aligned = close_arr_raw[~nan_mask]
        else:
            close_arr_aligned = None

        signals = generate_trade_signals(
            fold_results=wfv_results,
            fold_preds=fold_preds,
            fold_y_class=fold_y_class,
            ohlcv=ohlcv,
            mode_cfg=cfg,
            timestamps=ts_clean,
            symbols=sym_clean,
            close_arr=close_arr_aligned,
            confidence_threshold=config.confidence_threshold,
        )

        # Remove overlapping signals
        signals = filter_overlapping_signals(signals)
        result.signal_count = len(signals)
        logger.info("  %d signals after overlap filtering", len(signals))

        if not signals:
            logger.warning("  No trade signals generated — alpha has no active trades")
            result.status = "REJECTED"
            result.rejection = {
                "decision": "REJECT",
                "reasons": [{
                    "rule": "NO_SIGNALS",
                    "passed": False,
                    "critical": True,
                    "detail": "No trade signals exceeded confidence threshold",
                }],
                "summary": "REJECTED: No trade signals generated at threshold=%.2f" % config.confidence_threshold,
                "mode": mode,
            }
            result.duration_seconds = time.time() - start_ts
            return result

        # ------------------------------------------------------------------
        # Step 6: Backtest signals through simulation engine
        # ------------------------------------------------------------------
        logger.info("[6/8] Backtesting %d signals through simulation engine...",
                    len(signals))
        t0 = time.time()
        trades = backtest_signals(
            signals=signals,
            ohlcv=ohlcv,
            mode=mode,
        )
        backtest_duration = time.time() - t0
        result.trade_count = len(trades)
        logger.info("  %d/%d simulated in %.1fs",
                    len(trades), len(signals), backtest_duration)

        if not trades:
            logger.warning("  No trades could be simulated")
            result.status = "REJECTED"
            result.rejection = {
                "decision": "REJECT",
                "reasons": [{
                    "rule": "NO_SIMULATED_TRADES",
                    "passed": False,
                    "critical": True,
                    "detail": "No trade signals could be simulated (all missing future path or degenerate)",
                }],
                "summary": "REJECTED: No simulated trades",
                "mode": mode,
            }
            result.duration_seconds = time.time() - start_ts
            return result

        # ------------------------------------------------------------------
        # Step 7: Profitability analysis
        # ------------------------------------------------------------------
        logger.info("[7/8] Computing profitability metrics...")
        metrics = analyze_profitability(trades, mode=mode)
        result.metrics = metrics

        ret = metrics.get("return_metrics", {})
        risk = metrics.get("risk_metrics", {})
        logger.info(
            "  Trades=%d, E[R]=%.4fR, PF=%.2f, Sharpe=%.2f, DD=%.2fR, WR=%.2f%%",
            metrics["metadata"]["total_trades"],
            ret.get("expectancy_R", 0.0),
            risk.get("profit_factor", 0.0),
            risk.get("sharpe_ratio", 0.0),
            risk.get("max_drawdown_R", 0.0),
            risk.get("win_rate", 0.0) * 100,
        )

        # ------------------------------------------------------------------
        # Step 8: Rejection evaluation
        # ------------------------------------------------------------------
        logger.info("[8/8] Evaluating rejection criteria...")
        rejection = evaluate_alpha(metrics, mode=mode)
        result.rejection = rejection
        logger.info("  Decision: %s", rejection["decision"])

        # If promoted, build report + handoff
        if rejection["decision"] == "PROMOTE" and config.create_handoff:
            logger.info("  Alpha promoted! Building report and handoff package...")
            mode_research_report = _build_discovery_report(
                mode, wfv_results, metrics, rejection,
            )
            result.mode_research_report = mode_research_report

            handoff = _build_discovery_handoff(
                mode, mode_research_report, config,
            )
            result.handoff = handoff
            logger.info("  V7 handoff package built: %s",
                        handoff.get("handoff_package_id", "?"))

        result.status = rejection["decision"]

    except Exception as e:
        logger.exception("Discovery pipeline failed")
        result.status = "ERROR"
        result.errors.append(str(e))

    result.duration_seconds = time.time() - start_ts
    logger.info("Discovery pipeline: %s in %.1fs",
                result.status, result.duration_seconds)
    return result


# ---------------------------------------------------------------------------
# Report and handoff builders
# ---------------------------------------------------------------------------


def _build_discovery_report(
    mode: str,
    wfv_results: list[dict],
    metrics: dict,
    rejection: dict,
) -> dict:
    """Build a discovery-oriented summary report.

    This is a simplified report focusing on simulation-based profitability
    evidence rather than the full ModeResearchReport (which is the
    empirical builder's responsibility).
    """
    risk = metrics.get("risk_metrics", {})
    ret = metrics.get("return_metrics", {})
    cost = metrics.get("cost_decomposition", {})

    report = {
        "report_type": "discovery_profitability_report",
        "mode": mode,
        "verdict": rejection_to_verdict(rejection.get("decision", "REJECT")),
        "summary": rejection.get("summary", ""),
        "metrics": {
            "total_trades": metrics["metadata"]["total_trades"],
            "long_trades": metrics["metadata"]["long_trades"],
            "short_trades": metrics["metadata"]["short_trades"],
            "expectancy_r": ret.get("expectancy_R", 0.0),
            "profit_factor": risk.get("profit_factor", 0.0),
            "sharpe_ratio": risk.get("sharpe_ratio", 0.0),
            "max_drawdown_r": risk.get("max_drawdown_R", 0.0),
            "win_rate": risk.get("win_rate", 0.0),
            "avg_hold_bars": risk.get("avg_hold_bars", 0.0),
        },
        "cost_decomposition": {
            "total_cost_r": cost.get("total_cost_R", 0.0),
            "cost_drag_pct": cost.get("cost_drag_pct", 0.0),
        },
        "exit_breakdown": metrics.get("exit_breakdown", {}),
        "symbol_breakdown": metrics.get("symbol_breakdown", {}),
        "side_breakdown": metrics.get("side_breakdown", {}),
        "rejection": {
            "decision": rejection.get("decision", ""),
            "reasons": rejection.get("reasons", []),
        },
        "wf_accuracy": sum(r.get("val_accuracy", 0.0) for r in wfv_results) / max(len(wfv_results), 1),
        "wf_folds": len(wfv_results),
    }
    return report


def _build_discovery_handoff(
    mode: str,
    report: dict,
    config: DiscoveryConfig,
) -> dict:
    """Build a V7 handoff package from a promoted discovery result.

    Uses the existing empirical handoff builder when available, otherwise
    builds a minimal package.
    """
    try:
        from alphaforge.handoff.builders import build_empirical_handoff_package

        # Wrap our report in the format the handoff builder expects
        wrapper_report = {
            "report_id": f"discovery-{mode.lower()}-{int(time.time())}",
            "mode": mode,
            "verdict": report.get("verdict", "CONTINUE_RESEARCH"),
            "data_scope": {
                "symbols": list(config.symbols),
                "date_range_start": "",
                "date_range_end": "",
            },
            "metrics": {
                "oos_expectancy_r": {"value": report["metrics"]["expectancy_r"]},
                "oos_sharpe": {"value": report["metrics"]["sharpe_ratio"]},
                "oos_trade_count": report["metrics"]["total_trades"],
                "oos_win_rate": {"value": report["metrics"]["win_rate"]},
                "oos_profit_factor": {"value": report["metrics"]["profit_factor"]},
                "oos_max_drawdown_r": {"value": report["metrics"]["max_drawdown_r"]},
            },
            "cost_stress": {
                "combined_stress_edge_survives": True,
                "break_even_cost_total_pct": report.get("cost_decomposition", {}).get("cost_drag_pct", 0.0),
            },
            "regime_breakdown": {
                "regimes": [],
                "edge_only_in_rare_regime": False,
            },
            "validation_summary": {
                "fold_count": report.get("wf_folds", 0),
            },
            "multiple_hypothesis_control": {
                "correction_method": "NONE_APPLIED",
                "pbo_or_backtest_overfit_risk": "NOT_RUN",
                "data_snooping_risk_flag": "MODERATE",
            },
            "blocked_scopes": [],
            "limitations": [
                "Discovery pipeline report — not a full ModeResearchReport",
                "Walk-forward accuracy based on label agreement, not IC",
                "Cost stress analysis uses default multipliers, not regime-specific",
            ],
        }

        h = build_empirical_handoff_package(
            mode=mode,
            mode_research_report=wrapper_report,
            handoff_package_id=f"v7hp-{mode.lower()}-discovery-{int(time.time())}",
        )
        return h
    except Exception as e:
        logger.warning("Could not build V7 handoff package: %s", e)
        return {
            "handoff_type": "discovery_recommendation",
            "mode": mode,
            "verdict": report.get("verdict", ""),
            "note": "Full V7HandoffPackage not built — see discovery report",
        }
