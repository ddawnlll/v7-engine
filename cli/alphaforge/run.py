"""AlphaForge CLI — centralized command and control.

Commands:
    status      Show all alphas, their metrics, and simulation results
    discover    Run discovery pipelines (XSMOM, ML training)
    simulate    Run simulation on alpha(s) for profitability testing
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("alphaforge.cli")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="AlphaForge CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # status
    sub.add_parser("status", help="Show all alphas and their metrics")

    # discover
    discover_p = sub.add_parser("discover", help="Run all discovery pipelines")
    discover_p.add_argument("--mode", choices=["SWING", "SCALP", "AGGRESSIVE_SCALP"],
                            default="SWING", help="Mode to discover for")
    discover_p.add_argument("--real", action="store_true",
                            help="Actually run, not dry-run")

    # simulate
    sim_p = sub.add_parser("simulate", help="Run simulation on alpha(s)")
    sim_p.add_argument("alpha_id", nargs="?", default=None,
                       help="Alpha ID to simulate (omit with --all)")
    sim_p.add_argument("--all", dest="all_alphas", action="store_true",
                       help="Simulate all registered alphas")
    sim_p.add_argument("--real", action="store_true",
                       help="Actually run, not dry-run")

    # report
    report_p = sub.add_parser("report", help="Generate research reports (centralized)")
    from cli.alphaforge.report_cmd import build_report_parser
    build_report_parser(report_p)

    args = parser.parse_args()

    if args.command == "status":
        return cmd_status()
    elif args.command == "discover":
        return cmd_discover(args)
    elif args.command == "simulate":
        return cmd_simulate(args)
    elif args.command == "report":
        from cli.alphaforge.report_cmd import cmd_report
        return cmd_report(args)
    else:
        parser.print_help()
        return 1


def cmd_status() -> int:
    """Show all discovered alphas and their metrics."""
    alphas = _load_alpha_registry()

    print("=" * 72)
    print("  AlphaForge — Alpha Dashboard")
    print("=" * 72)

    if not alphas:
        print("  No alphas discovered yet.")
        print("  Run: python3 -m cli.alphaforge discover")
        return 0

    print()
    print(f"  {'ALPHA ID':<24} {'TYPE':<18} {'IC':>8} {'RnkIC':>8} {'Sharpe':>8} {'PF':>8} {'NetR':>10} {'Status':<12}")
    print(f"  {'─'*24} {'─'*18} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*10} {'─'*12}")

    for aid, alpha in alphas.items():
        m = alpha.get("metrics", {})
        ic = m.get("oos_ic", m.get("ic", "—"))
        rank_ic = m.get("oos_rank_ic", m.get("rank_ic", "—"))
        sharpe = m.get("oos_sharpe", m.get("sharpe", "—"))
        pf = m.get("profit_factor", m.get("pf", "—"))
        net_r = m.get("net_return", m.get("net_R", "—"))
        status = alpha.get("status", "UNKNOWN")

        ic_s = f"{ic:>7.3f}" if isinstance(ic, (int, float)) else f"{str(ic):>8}"
        ri_s = f"{rank_ic:>7.3f}" if isinstance(rank_ic, (int, float)) else f"{str(rank_ic):>8}"
        sp_s = f"{sharpe:>7.2f}" if isinstance(sharpe, (int, float)) else f"{str(sharpe):>8}"
        pf_s = f"{pf:>7.2f}" if isinstance(pf, (int, float)) else f"{str(pf):>8}"
        nr_s = f"{net_r:>+9.2%}" if isinstance(net_r, (int, float)) else f"{str(net_r):>10}"

        print(f"  {aid:<24} {alpha.get('type','?'):<18} {ic_s} {ri_s} {sp_s} {pf_s} {nr_s} {status:<12}")

    print()
    print(f"  Total alphas: {len(alphas)}")
    _print_simulation_summary(alphas)

    return 0


def _print_simulation_summary(alphas: dict) -> None:
    """Print summary of simulation results if any."""
    has_sim = any(a.get("simulation") for a in alphas.values())
    if not has_sim:
        print("  No simulation results yet.")
        print("  Run: python3 -m cli.alphaforge simulate --all")
        return

    print()
    print("  Simulation Results (cost-honest):")
    print(f"  {'ALPHA ID':<24} {'Net R':>10} {'Sharpe':>8} {'PF':>8} {'Drawdown':>10}")
    print(f"  {'─'*24} {'─'*10} {'─'*8} {'─'*8} {'─'*10}")
    for aid, alpha in alphas.items():
        sim = alpha.get("simulation")
        if sim:
            print(f"  {aid:<24} {sim.get('net_R',0):>+9.3f} {sim.get('sharpe',0):>7.2f} {sim.get('profit_factor',0):>7.2f} {sim.get('max_drawdown',0):>9.1%}")


def cmd_discover(args: argparse.Namespace) -> int:
    """Run discovery pipelines."""
    mode = args.mode
    real = args.real

    if not real:
        print(f"  Dry-run: would discover alphas for {mode}")
        print(f"  Use --real to execute")
        print()
        print("  Discovery pipelines:")
        print("    1. XSMOM baseline (cross-sectional momentum)")
        print("    2. ML training (XGBoost)")
        print("    3. Funding signal")
        return 0

    print(f"  Discovering alphas for {mode}...")
    # This is where we'd call the actual pipelines
    # For now, placeholder
    print("  (Implementation in progress)")
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    """Run simulation on alpha(s)."""
    alphas = _load_alpha_registry()

    if not alphas:
        print("  No alphas to simulate.")
        return 0

    if args.all_alphas:
        targets = list(alphas.keys())
    elif args.alpha_id:
        if args.alpha_id not in alphas:
            print(f"  Alpha '{args.alpha_id}' not found.")
            return 1
        targets = [args.alpha_id]
    else:
        print("  Specify an alpha ID or --all")
        return 1

    if not args.real:
        print(f"  Dry-run: would simulate {len(targets)} alpha(s)")
        print(f"  Use --real to execute")
        for t in targets:
            a = alphas[t]
            print(f"    {t} ({a.get('type','?')})")
        return 0

    print(f"  Running simulation on {len(targets)} alpha(s)...")
    for t in targets:
        result = _simulate_alpha(t, alphas[t])
        print(f"    {t}: net_R={result.get('net_R',0):+.3f}, "
              f"Sharpe={result.get('sharpe',0):.2f}, "
              f"PF={result.get('profit_factor',0):.2f}")
        alphas[t]["simulation"] = result

    _save_alpha_registry(alphas)
    return 0


def _simulate_alpha(alpha_id: str, alpha: dict) -> dict:
    """Run simulation on an alpha (placeholder)."""
    # In real implementation, this would:
    # 1. Load the alpha's trading rules/signals
    # 2. Run them through simulation engine
    # 3. Return cost-honest metrics
    mode = alpha.get("mode", "SWING")
    return {
        "net_R": 0.0,
        "sharpe": 0.0,
        "profit_factor": 0.0,
        "max_drawdown": 0.0,
        "trade_count": 0,
        "mode": mode,
        "status": "SIMULATED",
    }


# ── Registry ────────────────────────────────────────────────────────

ALPHA_REGISTRY_PATH = REPO_ROOT / "contracts" / "alpha_registry.json"


def _load_alpha_registry() -> dict[str, Any]:
    """Load alpha registry from disk."""
    if ALPHA_REGISTRY_PATH.exists():
        try:
            with open(ALPHA_REGISTRY_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_alpha_registry(registry: dict[str, Any]) -> None:
    """Save alpha registry to disk."""
    ALPHA_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ALPHA_REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2, default=str)
    print(f"  Registry saved to {ALPHA_REGISTRY_PATH}")


def register_alpha(
    alpha_id: str,
    alpha_type: str,
    mode: str,
    metrics: dict,
    status: str = "DISCOVERED",
) -> None:
    """Register or update an alpha in the registry."""
    registry = _load_alpha_registry()
    existing = registry.get(alpha_id, {})
    existing.update({
        "alpha_id": alpha_id,
        "type": alpha_type,
        "mode": mode,
        "metrics": metrics,
        "status": status,
    })
    registry[alpha_id] = existing
    _save_alpha_registry(registry)


if __name__ == "__main__":
    sys.exit(main())
