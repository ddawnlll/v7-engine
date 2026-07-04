"""Leaderboard generation — writes CSV and MD reports from evaluation results."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


REPORTS_DIR = Path("reports/alphaforge/factor_sprint")


def write_alpha_leaderboard(results: list[dict], output_path: Path | None = None) -> Path:
    """Write ALPHA_LEADERBOARD.csv from evaluation results.

    Args:
        results: List of dicts from evaluate_factor().
        output_path: Override path. Defaults to reports/alphaforge/factor_sprint/ALPHA_LEADERBOARD.csv.

    Returns:
        Path to written CSV.
    """
    if output_path is None:
        output_path = REPORTS_DIR / "ALPHA_LEADERBOARD.csv"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(results)

    # Sort: PASS first, then WATCH, then FAIL; within each group by |mean_rank_ic| desc
    sort_order = {"PASS": 0, "WATCH": 1, "FAIL": 2}
    df["_sort_pf"] = df["pass_fail"].map(sort_order).fillna(3)
    df["_sort_ic"] = df["mean_rank_ic"].abs().fillna(0)
    df = df.sort_values(["_sort_pf", "_sort_ic"], ascending=[True, False])
    df = df.drop(columns=["_sort_pf", "_sort_ic"])

    # Add rank column
    df.insert(0, "rank", range(1, len(df) + 1))

    df.to_csv(output_path, index=False)
    print(f"[leaderboard] Wrote ALPHA_LEADERBOARD.csv: {len(df)} rows")
    return output_path


def write_alpha_r_leaderboard(results: list[dict], output_path: Path | None = None) -> Path:
    """Write ALPHA_R_LEADERBOARD.csv from R simulation results.

    Args:
        results: List of dicts from aggregate_trades().
        output_path: Override path.

    Returns:
        Path to written CSV.
    """
    if output_path is None:
        output_path = REPORTS_DIR / "ALPHA_R_LEADERBOARD.csv"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(results)

    # Sort: PROMOTE first, then WATCH, then REJECT; within each group by total_R desc
    sort_order = {"PROMOTE_TO_MINI_V7": 0, "WATCH": 1, "REJECT": 2}
    df["_sort_pf"] = df["pass_fail"].map(sort_order).fillna(3)
    df = df.sort_values(["_sort_pf", "total_R"], ascending=[True, False])
    df = df.drop(columns=["_sort_pf"])

    # Add rank column
    df.insert(0, "rank", range(1, len(df) + 1))

    df.to_csv(output_path, index=False)
    print(f"[leaderboard] Wrote ALPHA_R_LEADERBOARD.csv: {len(df)} rows")
    return output_path


def generate_v7_alpha_candidates(
    r_results: list[dict],
    ic_results: list[dict],
    output_path: Path | None = None,
) -> Path:
    """Generate V7_ALPHA_CANDIDATES.md from R simulation and IC results.

    Only includes candidates that PASS or are strong WATCH.
    """
    if output_path is None:
        output_path = REPORTS_DIR / "V7_ALPHA_CANDIDATES.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Filter for PROMOTE or WATCH
    candidates = [r for r in r_results if r.get("pass_fail") in ("PROMOTE_TO_MINI_V7", "WATCH")]

    # Also find IC results for matching alpha names
    ic_by_name: dict[str, list[dict]] = {}
    for ic in ic_results:
        name = ic.get("factor_name", "")
        ic_by_name.setdefault(name, []).append(ic)

    lines = [
        "# V7 Alpha Candidates — Factor Sprint 001",
        "",
        f"Generated from {len(r_results)} total R-simulated factor-config combinations.",
        f"Promoted: {sum(1 for r in r_results if r.get('pass_fail') == 'PROMOTE_TO_MINI_V7')}",
        f"Watch: {sum(1 for r in r_results if r.get('pass_fail') == 'WATCH')}",
        f"Rejected: {sum(1 for r in r_results if r.get('pass_fail') == 'REJECT')}",
        "",
    ]

    if not candidates:
        lines.append("## No Candidates Ready")
        lines.append("")
        lines.append("No candidate meets the PROMOTE or WATCH threshold.")
        lines.append("The lab still succeeded because it produced real negative evidence.")
        lines.append("")
        lines.append("### Rejected Summary")
        for r in r_results:
            lines.append(f"- {r['alpha_name']} ({r['config_name']}): {r.get('notes', 'N/A')}")
    else:
        for i, c in enumerate(candidates, 1):
            name = c["alpha_name"]
            config = c["config_name"]

            # Find IC evidence
            ic_evidence = ic_by_name.get(name, [])
            ic_lines = []
            for ic in ic_evidence:
                ic_lines.append(
                    f"  - {ic['horizon']}h: IC={ic['mean_rank_ic']:.4f}, "
                    f"IC_IR={ic['ic_ir']:.4f}, spread={ic['top_bottom_net_return']:.4f}"
                )

            status_label = "PROMOTE" if c["pass_fail"] == "PROMOTE_TO_MINI_V7" else "WATCH"

            lines.extend([
                f"## Candidate {i}: {name} ({config})",
                "",
                f"- **Status:** {status_label}",
                f"- **Source factor:** {name}",
                f"- **Timeframe:** {c.get('side_mode', 'N/A')}",
                f"- **Direction:** {c.get('side_mode', 'N/A')}",
                f"- **Trade config:** {config}",
                f"- **Rank-IC evidence:**",
            ])
            if ic_lines:
                lines.extend(ic_lines)
            else:
                lines.append("  - (no IC evidence available)")

            lines.extend([
                f"- **R evidence:** total_R={c['total_R']:.4f}, "
                f"PF={c['profit_factor']:.2f}, "
                f"E[R]={c['expectancy_R']:.6f}, "
                f"win_rate={c['win_rate']:.1%}",
                f"- **Fee/slippage assumption:** 0.12% round trip "
                f"(0.04% taker + 0.02% slippage per side)",
                f"- **Best symbol:** {c['best_symbol']}",
                f"- **Worst symbol:** {c['worst_symbol']}",
                f"- **Dominant symbol share:** {c['dominant_symbol_share']:.0%}",
                f"- **Failure mode:** {c.get('notes', 'N/A')}",
                f"- **Suggested V7 action mapping:**",
                f"  - LONG_NOW: if factor rank >= top 20%",
                f"  - SHORT_NOW: if factor rank <= bottom 20%",
                f"  - NO_TRADE: middle 60%",
                f"- **Next test:** Out-of-sample on 2026 Q3 data, regime split",
                "",
            ])

    content = "\n".join(lines) + "\n"
    output_path.write_text(content)
    print(f"[leaderboard] Wrote V7_ALPHA_CANDIDATES.md: {len(candidates)} candidates")
    return output_path
