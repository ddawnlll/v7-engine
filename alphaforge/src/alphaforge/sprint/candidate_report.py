"""Top candidate report generator for the AlphaForge profitability sprint.

Produces markdown reports for top factor candidates with metrics, gate results,
and mode recommendations. Pure functional.
"""

from __future__ import annotations

from dataclasses import dataclass

from alphaforge.sprint.eval_gate import EvalGate
from alphaforge.sprint.runner import FactorResult


@dataclass(frozen=True)
class CandidateReport:
    """Markdown report for a single top candidate."""

    factor_name: str
    markdown: str


class CandidateReporter:
    """Generates markdown reports for top factor candidates."""

    def report(
        self,
        top_factors: list[FactorResult],
        eval_gates: dict[str, EvalGate],
    ) -> str:
        """Generate a combined markdown report for all top candidates.

        Parameters
        ----------
        top_factors : list[FactorResult]
            Top N factor results to report on.
        eval_gates : dict[str, EvalGate]
            Mapping of factor_name -> EvalGate results.

        Returns
        -------
        str
            Full markdown report.
        """
        lines: list[str] = []
        lines.append("# Profitability Sprint — Top Candidates")
        lines.append("")
        lines.append(f"**Candidates reviewed:** {len(top_factors)}")
        lines.append("")

        for i, factor in enumerate(top_factors, 1):
            gate = eval_gates.get(factor.factor_name)
            lines.extend(self._single_candidate_section(i, factor, gate))

        lines.append("---")
        lines.append("")
        lines.append("## Summary")
        lines.append("")

        passed = [f for f in top_factors if eval_gates.get(f.factor_name, EvalGate(gates=[], overall_pass=False, summary="")).overall_pass]
        failed = [f for f in top_factors if not eval_gates.get(f.factor_name, EvalGate(gates=[], overall_pass=False, summary="")).overall_pass]

        lines.append(f"- **Gate PASS:** {len(passed)}")
        lines.append(f"- **Gate FAIL:** {len(failed)}")
        lines.append("")

        if passed:
            lines.append("### Recommended for further evaluation")
            lines.append("")
            for f in passed:
                lines.append(f"- **{f.factor_name}** ({f.direction}, {f.horizon}h): net_return={f.net_return:.4f}, expectancy_r={f.expectancy_r:.4f}")
            lines.append("")

        if failed:
            lines.append("### Rejected")
            lines.append("")
            for f in failed:
                gate = eval_gates.get(f.factor_name)
                failed_gates = [g.gate_name for g in gate.gates if not g.passed] if gate else ["NO_GATE"]
                lines.append(f"- **{f.factor_name}**: {', '.join(failed_gates)}")
            lines.append("")

        return "\n".join(lines)

    def _single_candidate_section(
        self,
        rank: int,
        factor: FactorResult,
        gate: EvalGate | None,
    ) -> list[str]:
        """Generate markdown section for a single candidate."""
        lines: list[str] = []
        status = "✅ PASS" if gate and gate.overall_pass else "❌ FAIL"

        lines.append(f"## #{rank} {factor.factor_name} — {status}")
        lines.append("")
        lines.append(f"**Direction:** {factor.direction} | **Horizon:** {factor.horizon}h")
        lines.append("")

        # Metrics table
        lines.append("### Metrics")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Mean Rank IC | {factor.mean_ic:.4f} |")
        lines.append(f"| IC IR | {factor.ic_ir:.4f} |")
        lines.append(f"| Gross Return | {factor.gross_return:.4f} |")
        lines.append(f"| Net Return | {factor.net_return:.4f} |")
        lines.append(f"| Expectancy R | {factor.expectancy_r:.4f} |")
        lines.append(f"| Profit Factor | {factor.profit_factor:.2f} |")
        lines.append(f"| Max Drawdown | {factor.max_drawdown:.2%} |")
        lines.append(f"| Win Rate | {factor.win_rate:.2%} |")
        lines.append(f"| Turnover | {factor.turnover:.2%} |")
        lines.append(f"| Cost Drag | {factor.cost_drag:.4f} |")
        lines.append(f"| Trade Count | {factor.trade_count} |")
        lines.append("")

        # Gate results
        if gate:
            lines.append("### Gate Results")
            lines.append("")
            lines.append("| Gate | Status | Value | Threshold |")
            lines.append("|------|--------|-------|-----------|")
            for g in gate.gates:
                status_icon = "✅" if g.passed else "❌"
                lines.append(f"| {g.gate_name} | {status_icon} | {g.value:.4f} | {g.threshold:.4f} |")
            lines.append("")

        # Cost survival analysis
        lines.append("### Cost Survival")
        lines.append("")
        if factor.cost_drag > 0 and factor.gross_return != 0:
            cost_pct = abs(factor.cost_drag / factor.gross_return) * 100
            lines.append(f"- Costs consume **{cost_pct:.1f}%** of gross return")
            if cost_pct < 20:
                lines.append("- **Strong cost survival** — alpha is robust to transaction costs")
            elif cost_pct < 50:
                lines.append("- **Moderate cost survival** — alpha survives but is weakened")
            else:
                lines.append("- **Weak cost survival** — costs nearly destroy the alpha")
        else:
            lines.append("- No cost data available")
        lines.append("")

        # Mode recommendation
        lines.append("### Mode Recommendation")
        lines.append("")
        if factor.horizon <= 4:
            lines.append("- **SCALP** or **AGGRESSIVE_SCALP** — short holding period")
        elif factor.horizon <= 12:
            lines.append("- **SCALP** — medium holding period")
        else:
            lines.append("- **SWING** — longer holding period")
        lines.append("")

        # Notes
        if factor.notes:
            lines.append("### Notes")
            lines.append("")
            for note in factor.notes:
                lines.append(f"- {note}")
            lines.append("")

        lines.append("---")
        lines.append("")
        return lines
