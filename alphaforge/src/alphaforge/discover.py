"""AlphaForge Discovery CLI — end-to-end profit-seeking alpha discovery.

Usage:
    python -m alphaforge.discover --mode SWING --synthetic --symbols BTCUSDT,ETHUSDT,SOLUSDT

Runs the full pipeline: data → features → WFV → signal generation →
simulation backtest → profitability analysis → rejection or promotion.

Output:
    On success (PROMOTE): structured JSON report with V7 handoff package.
    On rejection: structured JSON with rejection reasons.
    On error: error message and exit code 2.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from alphaforge.discovery import DiscoveryConfig, DiscoveryResult
from alphaforge.discovery.pipeline import run_discovery

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger("alphaforge.discover")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="AlphaForge Discovery Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Run with synthetic data (quick test)\n"
            "  python -m alphaforge.discover --mode SWING --synthetic\n\n"
            "  # Run with panel cache\n"
            "  python -m alphaforge.discover --mode SCALP "
            "--panel-cache cache/factor_sprint\n\n"
            "  # Run with custom thresholds\n"
            "  python -m alphaforge.discover --mode SWING "
            "--confidence-threshold 0.7 --min-profit-factor 1.5\n"
        ),
    )
    p.add_argument(
        "--mode", default="SWING",
        choices=["SWING", "SCALP", "AGGRESSIVE_SCALP"],
        help="Trading mode (default: SWING)",
    )
    p.add_argument(
        "--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT",
        help="Comma-separated symbols (default: BTCUSDT,ETHUSDT,SOLUSDT)",
    )
    p.add_argument(
        "--features", default="all",
        help="Feature groups or 'all' (default: all)",
    )
    p.add_argument(
        "--folds", type=int, default=6,
        help="Walk-forward fold count (default: 6)",
    )
    p.add_argument(
        "--confidence-threshold", type=float, default=0.55,
        help="Min softmax confidence for directional trades (default: 0.55)",
    )
    p.add_argument(
        "--synthetic", action="store_true",
        help="Force synthetic data (no real data loading)",
    )
    p.add_argument(
        "--n-bars", type=int, default=3000,
        help="Synthetic bar count (default: 3000, synthetic only)",
    )
    p.add_argument(
        "--panel-cache", default=None,
        help="Path to factor_sprint panel cache directory",
    )
    p.add_argument(
        "--data-dir", default=None,
        help="Path to raw parquet data directory",
    )
    p.add_argument(
        "--output", "-o", default=None,
        help="Output JSON path (default: stdout)",
    )
    p.add_argument(
        "--no-handoff", action="store_true",
        help="Skip V7 handoff package creation",
    )
    p.add_argument(
        "--seed", type=int, default=42,
        help="Random seed (default: 42)",
    )
    return p


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    config = DiscoveryConfig(
        mode=args.mode.upper(),
        symbols=tuple(s.strip().upper() for s in args.symbols.split(",")),
        features=args.features,
        folds=args.folds,
        confidence_threshold=args.confidence_threshold,
        use_synthetic=args.synthetic,
        n_bars=args.n_bars,
        panel_cache=args.panel_cache,
        data_dir=args.data_dir,
        create_handoff=not args.no_handoff,
        random_seed=args.seed,
    )

    logger.info("AlphaForge Discovery Pipeline starting...")
    logger.info("Mode: %s | Symbols: %s | Threshold: %.2f | Folds: %d",
                config.mode, config.symbols, config.confidence_threshold, config.folds)

    result = run_discovery(config)

    # Build output
    output = {
        "status": result.status,
        "mode": config.mode,
        "symbols": list(config.symbols),
        "duration_seconds": round(result.duration_seconds, 2),
        "trade_count": result.trade_count,
        "signal_count": result.signal_count,
        "rejection": result.rejection,
        "metrics": result.metrics,
        "wf_accuracy": (
            result.wfv_metrics.get("accuracy", 0.0)
            if result.wfv_metrics else 0.0
        ),
        "wf_sharpe": (
            result.wfv_metrics.get("sharpe_ratio", 0.0)
            if result.wfv_metrics else 0.0
        ),
        "handoff": result.handoff,
        "errors": result.errors,
    }

    output_json = json.dumps(output, indent=2, default=str)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_json)
        logger.info("Output written to %s", out_path.resolve())
    else:
        print(output_json)

    # Exit code
    if result.status == "PROMOTE":
        logger.info("✓ Alpha PROMOTED — ready for V7 evaluation")
        return 0
    elif result.status == "REJECTED":
        logger.info("✗ Alpha REJECTED — see rejection reasons")
        return 1
    else:
        logger.error("✗ Pipeline failed: %s", result.errors)
        return 2


if __name__ == "__main__":
    sys.exit(main())
