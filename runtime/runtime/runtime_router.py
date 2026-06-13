"""Runtime router that dispatches operations by trade mode.

Supports trade-mode-aware routing for scan and inference operations,
with safe fallback when no mode-specific champion is available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from v6.contracts.enums import TradeMode
from v6.registry.model_registry import ModelArtifact, ModelRegistry


@dataclass(frozen=True)
class RoutedExecutionTarget:
    """Resolved execution target for a given trade mode."""

    trade_mode: TradeMode
    champion: ModelArtifact | None
    engine_name: str
    engine_version: str
    is_fallback: bool = False
    fallback_reason: str | None = None


class TradeModeRouter:
    """Routes runtime operations by trade mode.

    The router resolves the appropriate champion model for a given trade mode.
    If no mode-specific champion exists, it falls back to the global champion.
    """

    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self._registry = registry or ModelRegistry()

    def resolve(
        self,
        trade_mode: str | TradeMode,
    ) -> RoutedExecutionTarget:
        """Resolve the execution target for a given trade mode.

        Args:
            trade_mode: The trade mode to route for (e.g., SWING, SCALP, AGGRESSIVE_SCALP).

        Returns:
            A RoutedExecutionTarget with the resolved champion and engine info.
        """
        mode = TradeMode(trade_mode.upper() if isinstance(trade_mode, str) else trade_mode.value)

        # First try exact mode-specific champion match
        champion = self._registry.get_champion_for_trade_mode(mode.value, fallback=False)

        if champion is not None:
            return RoutedExecutionTarget(
                trade_mode=mode,
                champion=champion,
                engine_name=champion.engine_name,
                engine_version=champion.engine_version,
                is_fallback=False,
                fallback_reason=None,
            )

        # Fallback: try global champion
        fallback = self._registry.get_champion()
        if fallback is not None:
            return RoutedExecutionTarget(
                trade_mode=mode,
                champion=fallback,
                engine_name=fallback.engine_name,
                engine_version=fallback.engine_version,
                is_fallback=True,
                fallback_reason=f"No mode-specific champion for {mode.value}; using global champion",
            )

        # No champion at all — safe fallback
        return RoutedExecutionTarget(
            trade_mode=mode,
            champion=None,
            engine_name="v4_default",
            engine_version="0.0.0",
            is_fallback=True,
            fallback_reason=f"No champion available for trade mode {mode.value}; using safe default",
        )

    def get_engine_name(self, trade_mode: str | TradeMode) -> str:
        """Get the engine name for a given trade mode.

        Returns a safe default if no engine can be resolved.
        """
        target = self.resolve(trade_mode)
        return target.engine_name

    def get_champion(self, trade_mode: str | TradeMode) -> ModelArtifact | None:
        """Get the champion model artifact for a given trade mode.

        Returns None if no champion is available (caller should handle gracefully).
        """
        target = self.resolve(trade_mode)
        return target.champion

    @property
    def registry(self) -> ModelRegistry:
        return self._registry


class RuntimeRouterRegistry:
    """Registry of trade-mode routers for different runtime contexts.

    Maintains a collection of TradeModeRouter instances keyed by runtime context
    (e.g., scan, inference, execution).
    """

    def __init__(self) -> None:
        self._routers: dict[str, TradeModeRouter] = {}

    def get_router(self, context: str = "default") -> TradeModeRouter:
        """Get or create a router for the given context."""
        if context not in self._routers:
            self._routers[context] = TradeModeRouter()
        return self._routers[context]

    def register_router(self, context: str, router: TradeModeRouter) -> None:
        """Register a custom router for a given context."""
        self._routers[context] = router


# Shared singleton
_SHARED_ROUTER: TradeModeRouter | None = None


def get_shared_runtime_router() -> TradeModeRouter:
    """Get the shared singleton runtime router."""
    global _SHARED_ROUTER
    if _SHARED_ROUTER is None:
        _SHARED_ROUTER = TradeModeRouter()
    return _SHARED_ROUTER
