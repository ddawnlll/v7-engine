"""Position limit guard — rejects trades that would exceed configured exposure ceilings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PositionLimitConfig:
    """Configuration for position exposure limits."""

    max_positions: int = 10
    max_notional_per_position: float = 50_000.0
    max_total_notional: float = 200_000.0
    max_leverage: float = 10.0


@dataclass(frozen=True)
class LimitViolation:
    """Describes why a proposed trade was rejected."""

    rule: str
    message: str
    current: float
    limit: float


class PositionLimiter:
    """Evaluates whether a proposed trade stays within configured position limits."""

    def __init__(self, config: PositionLimitConfig | None = None) -> None:
        self.config = config or PositionLimitConfig()

    def reject_if_over_limit(
        self,
        proposed_notional: float,
        current_positions: list[dict[str, Any]],
    ) -> LimitViolation | None:
        """Return a LimitViolation if the proposed trade would breach any limit, else None."""
        active_count = len(current_positions)
        total_notional = sum(abs(float(p.get("notional", 0))) for p in current_positions)

        # Check max number of positions
        if active_count >= self.config.max_positions:
            return LimitViolation(
                rule="max_positions",
                message=f"Already at {active_count} positions (limit {self.config.max_positions})",
                current=float(active_count),
                limit=float(self.config.max_positions),
            )

        # Check per-position notional ceiling
        if proposed_notional > self.config.max_notional_per_position:
            return LimitViolation(
                rule="max_notional_per_position",
                message=f"Proposed notional {proposed_notional} exceeds per-position cap {self.config.max_notional_per_position}",
                current=proposed_notional,
                limit=self.config.max_notional_per_position,
            )

        # Check aggregate notional ceiling
        projected_total = total_notional + proposed_notional
        if projected_total > self.config.max_total_notional:
            return LimitViolation(
                rule="max_total_notional",
                message=f"Projected total {projected_total} exceeds aggregate cap {self.config.max_total_notional}",
                current=projected_total,
                limit=self.config.max_total_notional,
            )

        return None
