"""
V7 Portfolio Manager — Correlation-Aware Exposure Controls.

Domain authority:
  - Owns cross-symbol portfolio interaction after single-candidate policy output
  - Does NOT invent alpha (AlphaForge owns discovery)
  - Does NOT own final trade decisions (V7 policy owns acceptance)
  - Does NOT own hard risk gates (RiskManager owns those)

Pipeline position: policy -> portfolio -> risk -> runtime execution eligibility

Design per:
  - v7/docs/pipeline/portfolio.md
  - v7/docs/implementation/phase_7_portfolio_risk_and_runtime_integration.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Default correlation groups (versioned — first-phase manual groupings)
# ---------------------------------------------------------------------------
CORRELATION_GROUPS: dict[str, set[str]] = {
    "btc_cluster": {"BTCUSDT", "WBTCUSDT"},
    "eth_cluster": {"ETHUSDT"},
    "layer1": {"SOLUSDT", "ADAUSDT", "DOTUSDT", "AVAXUSDT"},
    "defi": {"UNIUSDT", "AAVEUSDT", "MKRUSDT"},
}

DEFAULT_CONFIG: dict[str, Any] = {
    "max_position_pct": 10.0,
    "max_cluster_exposure_pct": 15.0,
    "max_total_exposure_pct": 50.0,
    "max_simultaneous_positions": 10,
    "correlation_groups": CORRELATION_GROUPS,
    "ranking_fields": ["expected_r_net", "confidence"],
}


# ---------------------------------------------------------------------------
# PortfolioResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PortfolioResult:
    """Output of portfolio evaluation.

    Attributes:
        suppressed: List of symbols that were suppressed.
        ranked: Remaining decisions after suppression, sorted by rank.
        exposure_remaining_pct: Remaining exposure capacity as % of account.
        concentration_warnings: Human-readable warnings about concentration.
    """

    suppressed: list[str] = field(default_factory=list)
    ranked: list[dict] = field(default_factory=list)
    exposure_remaining_pct: float = 100.0
    concentration_warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# PortfolioManager
# ---------------------------------------------------------------------------


def _rank_key(decision: dict) -> tuple:
    """Return a sort key for ranking decisions.

    Primary: expected_r_net (higher better).
    Secondary: confidence (higher better).
    Tertiary: symbol alphabetically for deterministic tie-break.
    """
    exp_r = decision.get("expected_r_net", decision.get("expected_r", 0.0))
    conf = decision.get("confidence", 0.0)
    symbol = decision.get("symbol", "")
    return (-exp_r, -conf, symbol)


def _get_symbol_exposure(decision: dict, positions: dict) -> float:
    """Get current exposure for a decision's symbol from positions."""
    symbol = decision.get("symbol", "")
    pos = positions.get(symbol, {})
    if isinstance(pos, dict):
        return float(pos.get("size_pct", pos.get("exposure_pct", 0.0)))
    return 0.0


def _get_correlation_group(symbol: str, groups: dict[str, set[str]]) -> str | None:
    """Return the correlation group name for a symbol, or None."""
    for group_name, members in groups.items():
        if symbol in members:
            return group_name
    return None


class PortfolioManager:
    """Portfolio-level exposure and concentration controls.

    Applies suppression rules after per-symbol policy acceptance:
      1. Over-concentration suppression (single-symbol)
      2. Correlated-bet suppression (cluster-level)
      3. Position limits (total count + total exposure)
    """

    def __init__(self, config: dict | None = None) -> None:
        self.config: dict[str, Any] = {**DEFAULT_CONFIG, **(config or {})}

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def evaluate_portfolio(
        self,
        requests: list[dict],
        results: list[dict],
        positions: dict[str, Any],
    ) -> PortfolioResult:
        """Evaluate a batch of policy-approved decisions against portfolio constraints.

        Args:
            requests: List of AnalysisRequest dicts (preserved for lineage).
            results: List of policy-result dicts (must have 'symbol' key).
            positions: Current positions dict {symbol: {size_pct, side, ...}}.

        Returns:
            PortfolioResult with suppression details and ranked decisions.
        """
        # Merge request and result data into unified decision records
        decisions = self._build_decisions(requests, results, positions)

        # Step 1: Compute symbol-level exposures
        symbol_exposure: dict[str, float] = {}
        for pos_symbol, pos_data in positions.items():
            if isinstance(pos_data, dict):
                symbol_exposure[pos_symbol] = float(
                    pos_data.get("size_pct", pos_data.get("exposure_pct", 0.0))
                )

        # Step 2: Suppress over-concentration
        concentration_warnings: list[str] = []
        decisions, conc_suppressed = self._suppress_overconcentration(
            decisions, symbol_exposure
        )
        concentration_warnings.extend(conc_suppressed)

        # Step 3: Suppress correlated bets via cluster limits
        decisions, corr_suppressed = self._suppress_correlated(
            decisions, self.config.get("correlation_groups", {}), positions
        )

        # Step 4: Apply position limits
        max_positions = self.config.get("max_simultaneous_positions", 10)
        max_exposure_pct = self.config.get("max_total_exposure_pct", 50.0)
        decisions, limit_suppressed = self._apply_position_limits(
            decisions, max_positions, max_exposure_pct, positions
        )

        # Rank remaining decisions
        ranked = sorted(decisions, key=_rank_key)

        # Compute remaining exposure
        used = sum(
            d.get("position_size_pct", d.get("size_pct", 0.0)) for d in ranked
        )
        for _, pos_data in positions.items():
            if isinstance(pos_data, dict):
                used += float(
                    pos_data.get("size_pct", pos_data.get("exposure_pct", 0.0))
                )

        exposure_remaining_pct = max(0.0, 100.0 - used)

        all_suppressed = list(
            dict.fromkeys(conc_suppressed + corr_suppressed + limit_suppressed)
        )

        return PortfolioResult(
            suppressed=all_suppressed,
            ranked=ranked,
            exposure_remaining_pct=round(exposure_remaining_pct, 2),
            concentration_warnings=concentration_warnings,
        )

    # ------------------------------------------------------------------
    # Public per-step methods (callable individually for testing/flexibility)
    # ------------------------------------------------------------------

    def suppress_overconcentration(
        self,
        decisions: list[dict],
        symbol_exposure: dict[str, float],
    ) -> list[dict]:
        """Suppress decisions for symbols exceeding per-symbol concentration limits.

        Lower rank for over-concentrated symbols. Symbols whose total
        exposure (current + proposed) exceeds max_position_pct are suppressed.

        Args:
            decisions: List of decision dicts, each with at least 'symbol'.
            symbol_exposure: Dict mapping symbol -> current exposure %.

        Returns:
            Filtered list with over-concentrated symbols removed.
        """
        filtered, _ = self._suppress_overconcentration(decisions, symbol_exposure)
        return filtered

    def suppress_correlated(
        self,
        decisions: list[dict],
        correlation_groups: dict[str, set[str]],
    ) -> list[dict]:
        """Suppress decisions from correlation groups exceeding cluster limits.

        When a cluster's combined exposure would exceed max_cluster_exposure_pct,
        the lowest-ranked decisions from that cluster are suppressed.

        Args:
            decisions: List of decision dicts.
            correlation_groups: Dict of {group_name: set_of_symbols}.

        Returns:
            Filtered list with correlated-excess symbols removed.
        """
        filtered, _ = self._suppress_correlated(decisions, correlation_groups)
        return filtered

    def apply_position_limits(
        self,
        decisions: list[dict],
        max_positions: int,
        max_exposure_pct: float,
    ) -> list[dict]:
        """Cap decisions by max position count and max total exposure.

        Decisions are ranked first; lowest-ranked are suppressed when
        limits are exceeded.

        Args:
            decisions: List of decision dicts.
            max_positions: Maximum number of simultaneous positions.
            max_exposure_pct: Maximum total exposure as % of account.

        Returns:
            Filtered list within limits.
        """
        filtered, _ = self._apply_position_limits(
            decisions, max_positions, max_exposure_pct
        )
        return filtered

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_decisions(
        self,
        requests: list[dict],
        results: list[dict],
        positions: dict[str, Any],
    ) -> list[dict]:
        """Merge requests and results into unified decision records."""
        # Index results by symbol for merging
        result_by_symbol: dict[str, dict] = {}
        for r in results:
            sym = r.get("symbol", r.get("request", {}).get("symbol", ""))
            if sym:
                result_by_symbol[sym] = r

        decisions: list[dict] = []
        seen_symbols: set[str] = set()
        for req in requests:
            sym = req.get("symbol", "")
            if not sym or sym in seen_symbols:
                continue
            seen_symbols.add(sym)
            result = result_by_symbol.get(sym, {})

            # Only include passed decisions
            passed = result.get("passed", result.get("policy_passed", True))
            if not passed:
                continue

            decision: dict[str, Any] = {
                "symbol": sym,
                "direction": result.get("decision", req.get("direction", "LONG")),
                "confidence": result.get("confidence", 0.0),
                "expected_r_net": result.get("expected_r", result.get("expected_r_net", 0.0)),
                "position_size_pct": result.get(
                    "position_size_pct",
                    result.get("size_pct", self.config.get("max_position_pct", 10.0)),
                ),
                "entry_price": result.get("entry_price", 0.0),
                "stop_loss_price": result.get("stop_loss_price", 0.0),
                "take_profit_price": result.get("take_profit_price", 0.0),
            }

            # Merge current position context
            pos = positions.get(sym, {})
            if isinstance(pos, dict):
                decision["current_position_side"] = pos.get("side", "NONE")
                decision["current_position_size_pct"] = float(
                    pos.get("size_pct", pos.get("exposure_pct", 0.0))
                )
            else:
                decision["current_position_side"] = "NONE"
                decision["current_position_size_pct"] = 0.0

            decisions.append(decision)

        return decisions

    def _suppress_overconcentration(
        self,
        decisions: list[dict],
        symbol_exposure: dict[str, float],
    ) -> tuple[list[dict], list[str]]:
        """Internal: suppress over-concentrated symbols, return (filtered, suppressed_symbols)."""
        max_pos_pct = self.config.get("max_position_pct", 10.0)
        filtered: list[dict] = []
        suppressed: list[str] = []

        for d in decisions:
            symbol = d.get("symbol", "")
            current = symbol_exposure.get(symbol, 0.0)
            proposed = d.get("position_size_pct", 0.0)
            total = current + proposed

            if total > max_pos_pct:
                suppressed.append(symbol)
            else:
                filtered.append(d)

        return filtered, suppressed

    def _suppress_correlated(
        self,
        decisions: list[dict],
        correlation_groups: dict[str, set[str]],
        positions: dict[str, Any] | None = None,
    ) -> tuple[list[dict], list[str]]:
        """Internal: suppress excess cluster exposure, return (filtered, suppressed_symbols)."""
        max_cluster_pct = self.config.get("max_cluster_exposure_pct", 15.0)
        if not correlation_groups:
            return decisions, []

        # Build reverse lookup: symbol -> group
        symbol_to_group: dict[str, str] = {}
        for gname, members in correlation_groups.items():
            for m in members:
                symbol_to_group[m] = gname

        # Seed cluster exposure with already-open positions.  Without this,
        # a newly admitted decision could exceed a cluster cap merely because
        # its correlated sibling was opened on a previous timestamp.
        cluster_exposure: dict[str, float] = {}
        if positions:
            for symbol, position in positions.items():
                if not isinstance(position, dict):
                    continue
                group = symbol_to_group.get(symbol)
                if group is not None:
                    cluster_exposure[group] = cluster_exposure.get(group, 0.0) + float(
                        position.get("size_pct", position.get("exposure_pct", 0.0))
                    )

        # Rank decisions (best first)
        ranked = sorted(decisions, key=_rank_key)

        # Track cluster exposure and suppress excess
        filtered: list[dict] = []
        suppressed: list[str] = []

        for d in ranked:
            symbol = d.get("symbol", "")
            group = symbol_to_group.get(symbol)
            proposed = d.get("position_size_pct", 0.0)

            if group is not None:
                current = cluster_exposure.get(group, 0.0)
                if current + proposed > max_cluster_pct:
                    suppressed.append(symbol)
                    continue
                cluster_exposure[group] = current + proposed

            # Not in any tracked group, or within limit — keep
            filtered.append(d)

        return filtered, suppressed

    def _apply_position_limits(
        self,
        decisions: list[dict],
        max_positions: int,
        max_exposure_pct: float,
        positions: dict[str, Any] | None = None,
    ) -> tuple[list[dict], list[str]]:
        """Internal: apply count + exposure caps, return (filtered, suppressed_symbols)."""
        if max_positions <= 0:
            return [], [d.get("symbol", "?") for d in decisions]

        # Rank decisions (best first)
        ranked = sorted(decisions, key=_rank_key)
        filtered: list[dict] = []
        suppressed: list[str] = []
        active_positions = {
            symbol for symbol, position in (positions or {}).items()
            if isinstance(position, dict) and float(
                position.get("size_pct", position.get("exposure_pct", 0.0))
            ) > 0.0
        }
        total_exposure = sum(
            float(position.get("size_pct", position.get("exposure_pct", 0.0)))
            for position in (positions or {}).values()
            if isinstance(position, dict)
        )

        for d in ranked:
            if len(active_positions) + len(filtered) >= max_positions:
                suppressed.append(d.get("symbol", "?"))
                continue

            proposed = d.get("position_size_pct", 0.0)
            if total_exposure + proposed > max_exposure_pct:
                suppressed.append(d.get("symbol", "?"))
                continue

            filtered.append(d)
            total_exposure += proposed

        return filtered, suppressed
