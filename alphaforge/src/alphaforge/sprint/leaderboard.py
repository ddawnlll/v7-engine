"""Leaderboard generation — writes CSV from SprintResult.

Pure functional: build() returns DataFrame, save() writes to disk.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from alphaforge.sprint.runner import SprintResult, FactorResult


class Leaderboard:
    """Builds and saves factor sprint leaderboards.

    Pure functional where possible. No state mutations.
    """

    def build(self, sprint_result: SprintResult) -> pd.DataFrame:
        """Build leaderboard DataFrame from SprintResult.

        Args:
            sprint_result: Result from FactorSprintRunner.run().

        Returns:
            DataFrame with rank, metrics, and pass/fail status.
        """
        if not sprint_result.factors:
            return pd.DataFrame()

        # Convert FactorResult list to dicts
        records = []
        for f in sprint_result.factors:
            records.append({
                "factor_name": f.factor_name,
                "horizon": f.horizon,
                "direction": f.direction,
                "mean_ic": f.mean_ic,
                "ic_ir": f.ic_ir,
                "gross_return": f.gross_return,
                "net_return": f.net_return,
                "expectancy_r": f.expectancy_r,
                "profit_factor": f.profit_factor,
                "max_drawdown": f.max_drawdown,
                "win_rate": f.win_rate,
                "turnover": f.turnover,
                "cost_drag": f.cost_drag,
                "trade_count": f.trade_count,
                "pass_fail": f.pass_fail,
                "notes": "; ".join(f.notes) if isinstance(f.notes, list) else str(f.notes),
            })

        df = pd.DataFrame(records)

        # Sort: PASS first (by net_expectancy_r desc), then WATCH, then FAIL
        sort_order = {"PASS": 0, "WATCH": 1, "FAIL": 2}
        df["_sort_pf"] = df["pass_fail"].map(sort_order).fillna(3)
        df["_sort_expectancy"] = df["expectancy_r"].fillna(-999.0)
        df = df.sort_values(
            ["_sort_pf", "_sort_expectancy"],
            ascending=[True, False],
        )
        df = df.drop(columns=["_sort_pf", "_sort_expectancy"])

        # Add rank column (1-indexed)
        df.insert(0, "rank", range(1, len(df) + 1))

        return df

    def save(
        self,
        df: pd.DataFrame,
        output_dir: str | Path = "reports/alphaforge/profit_sprint",
    ) -> Path:
        """Save leaderboard DataFrame to CSV.

        Args:
            df: Leaderboard DataFrame from build().
            output_dir: Directory to write CSV.

        Returns:
            Path to written CSV.
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        csv_path = output_path / "leaderboard.csv"
        df.to_csv(csv_path, index=False)

        print(f"[leaderboard] Wrote {csv_path}: {len(df)} rows")
        return csv_path
