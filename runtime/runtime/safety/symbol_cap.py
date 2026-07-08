"""Symbol exposure cap — limits per-symbol and aggregate crypto exposure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SymbolCapConfig:
    """Configuration for per-symbol and total exposure limits."""

    max_notional_per_symbol: float = 50_000.0
    max_total_notional: float = 200_000.0
    max_positions_per_symbol: int = 3
    max_symbols: int = 10


@dataclass(frozen=True)
class SymbolExposureViolation:
    rule: str
    message: str
    symbol: str
    current: float
    limit: float


class SymbolCap:
    """Evaluates whether a proposed trade stays within per-symbol and aggregate caps."""

    def __init__(self, config: SymbolCapConfig | None = None) -> None:
        self.config = config or SymbolCapConfig()

    def check_symbol_exposure(
        self,
        symbol: str,
        proposed_notional: float,
        current_exposures: dict[str, dict[str, Any]],
    ) -> SymbolExposureViolation | None:
        """Return a violation if the proposed trade breaches any cap, else None.

        ``current_exposures`` maps symbol → {"notional": float, "count": int}.
        """
        sym = current_exposures.get(symbol, {})
        current_notional = abs(float(sym.get("notional", 0)))
        current_count = int(sym.get("count", 0))

        # Per-symbol notional cap
        projected = current_notional + proposed_notional
        if projected > self.config.max_notional_per_symbol:
            return SymbolExposureViolation(
                rule="max_notional_per_symbol",
                message=f"Projected {symbol} notional {projected} exceeds cap {self.config.max_notional_per_symbol}",
                symbol=symbol,
                current=projected,
                limit=self.config.max_notional_per_symbol,
            )

        # Per-symbol position count cap
        if current_count >= self.config.max_positions_per_symbol:
            return SymbolExposureViolation(
                rule="max_positions_per_symbol",
                message=f"Symbol {symbol} already has {current_count} positions (limit {self.config.max_positions_per_symbol})",
                symbol=symbol,
                current=float(current_count),
                limit=float(self.config.max_positions_per_symbol),
            )

        # Aggregate notional cap
        total_notional = sum(
            abs(float(v.get("notional", 0))) for v in current_exposures.values()
        )
        projected_total = total_notional + proposed_notional
        if projected_total > self.config.max_total_notional:
            return SymbolExposureViolation(
                rule="max_total_notional",
                message=f"Projected total notional {projected_total} exceeds aggregate cap {self.config.max_total_notional}",
                symbol=symbol,
                current=projected_total,
                limit=self.config.max_total_notional,
            )

        # Max distinct symbols
        symbol_count = len(current_exposures)
        if symbol not in current_exposures and symbol_count >= self.config.max_symbols:
            return SymbolExposureViolation(
                rule="max_symbols",
                message=f"Already tracking {symbol_count} symbols (limit {self.config.max_symbols})",
                symbol=symbol,
                current=float(symbol_count),
                limit=float(self.config.max_symbols),
            )

        return None
