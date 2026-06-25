"""Tests for TradeModeRouter — mode-specific champion dispatch and fallback logic.

Coverage targets:
- Exact mode match resolution
- Fallback to global champion
- Safe default when no champion exists
- RuntimeRouterRegistry context switching
- Shared singleton lifecycle
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Mock v6 modules before importing runtime_router
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_v6_modules():
    """Inject fake v6.contracts.enums and v6.registry.model_registry modules."""
    # v6.contracts.enums
    class FakeTradeMode(Enum):
        SWING = "SWING"
        SCALP = "SCALP"
        AGGRESSIVE_SCALP = "AGGRESSIVE_SCALP"

    fake_enums = MagicMock()
    fake_enums.TradeMode = FakeTradeMode
    sys.modules["v6.contracts"] = MagicMock()
    sys.modules["v6.contracts.enums"] = fake_enums

    # v6.registry.model_registry
    @dataclass(frozen=True)
    class FakeModelArtifact:
        name: str = "test_model"
        engine_name: str = "xgb_v1"
        engine_version: str = "1.2.3"
        trade_mode: str = "SWING"
        accuracy: float = 0.85

    class FakeModelRegistry:
        def __init__(self, champions=None, global_champion=None):
            self._champions = champions or {}
            self._global_champion = global_champion

        def get_champion_for_trade_mode(self, mode: str, fallback: bool = False):
            return self._champions.get(mode)

        def get_champion(self):
            return self._global_champion

    fake_registry = MagicMock()
    fake_registry.ModelArtifact = FakeModelArtifact
    fake_registry.ModelRegistry = FakeModelRegistry
    sys.modules["v6.registry"] = MagicMock()
    sys.modules["v6.registry.model_registry"] = fake_registry

    yield

    # Cleanup
    for m in ["v6.contracts.enums", "v6.contracts", "v6.registry.model_registry", "v6.registry"]:
        sys.modules.pop(m, None)


# ---------------------------------------------------------------------------
# TradeModeRouter tests
# ---------------------------------------------------------------------------

class TestTradeModeRouterExactMatch:
    def test_resolves_swing_champion(self):
        from runtime.runtime.runtime_router import TradeModeRouter
        from v6.registry.model_registry import ModelRegistry

        champion = MagicMock()
        champion.engine_name = "swing_engine"
        champion.engine_version = "2.0.0"
        registry = ModelRegistry()
        registry._champions["SWING"] = champion
        router = TradeModeRouter(registry=registry)

        target = router.resolve("SWING")
        assert target.trade_mode.value == "SWING"
        assert target.champion is champion
        assert target.engine_name == "swing_engine"
        assert target.engine_version == "2.0.0"
        assert target.is_fallback is False
        assert target.fallback_reason is None

    def test_resolves_scalp_champion(self):
        from runtime.runtime.runtime_router import TradeModeRouter
        from v6.registry.model_registry import ModelRegistry

        champion = MagicMock()
        champion.engine_name = "scalp_engine"
        champion.engine_version = "1.0.0"
        registry = ModelRegistry()
        registry._champions["SCALP"] = champion
        router = TradeModeRouter(registry=registry)

        target = router.resolve("SCALP")
        assert target.trade_mode.value == "SCALP"
        assert target.champion is champion

    def test_accepts_trade_mode_enum(self):
        from runtime.runtime.runtime_router import TradeModeRouter
        from v6.contracts.enums import TradeMode
        from v6.registry.model_registry import ModelRegistry

        champion = MagicMock()
        champion.engine_name = "swing_v2"
        champion.engine_version = "2.1.0"
        registry = ModelRegistry()
        registry._champions["SWING"] = champion
        router = TradeModeRouter(registry=registry)

        target = router.resolve(TradeMode.SWING)
        assert target.trade_mode == TradeMode.SWING
        assert target.engine_name == "swing_v2"


class TestTradeModeRouterFallback:
    def test_falls_back_to_global_champion(self):
        from runtime.runtime.runtime_router import TradeModeRouter
        from v6.registry.model_registry import ModelRegistry

        global_champion = MagicMock()
        global_champion.engine_name = "global_engine"
        global_champion.engine_version = "3.0.0"
        registry = ModelRegistry()
        registry._global_champion = global_champion
        # No mode-specific champion for SCALP
        router = TradeModeRouter(registry=registry)

        target = router.resolve("SCALP")
        assert target.champion is global_champion
        assert target.is_fallback is True
        assert "No mode-specific champion" in target.fallback_reason

    def test_safe_default_when_no_champion_at_all(self):
        from runtime.runtime.runtime_router import TradeModeRouter
        from v6.registry.model_registry import ModelRegistry

        registry = ModelRegistry()  # No champions at all
        router = TradeModeRouter(registry=registry)

        target = router.resolve("SWING")
        assert target.champion is None
        assert target.is_fallback is True
        assert target.engine_name == "v4_default"
        assert target.engine_version == "0.0.0"
        assert "No champion available" in target.fallback_reason


class TestTradeModeRouterHelpers:
    def test_get_engine_name_returns_string(self):
        from runtime.runtime.runtime_router import TradeModeRouter
        from v6.registry.model_registry import ModelRegistry

        champion = MagicMock()
        champion.engine_name = "xgb_v3"
        champion.engine_version = "3.1.0"
        registry = ModelRegistry()
        registry._champions["SWING"] = champion
        router = TradeModeRouter(registry=registry)

        name = router.get_engine_name("SWING")
        assert name == "xgb_v3"

    def test_get_engine_name_fallback(self):
        from runtime.runtime.runtime_router import TradeModeRouter
        from v6.registry.model_registry import ModelRegistry

        router = TradeModeRouter(registry=ModelRegistry())
        name = router.get_engine_name("AGGRESSIVE_SCALP")
        assert name == "v4_default"

    def test_get_champion_returns_artifact(self):
        from runtime.runtime.runtime_router import TradeModeRouter
        from v6.registry.model_registry import ModelRegistry

        champion = MagicMock()
        champion.engine_name = "swing_model"
        registry = ModelRegistry()
        registry._champions["SWING"] = champion
        router = TradeModeRouter(registry=registry)

        artifact = router.get_champion("SWING")
        assert artifact is champion

    def test_get_champion_returns_none_when_no_match(self):
        from runtime.runtime.runtime_router import TradeModeRouter
        from v6.registry.model_registry import ModelRegistry

        router = TradeModeRouter(registry=ModelRegistry())
        artifact = router.get_champion("SCALP")
        assert artifact is None

    def test_registry_property(self):
        from runtime.runtime.runtime_router import TradeModeRouter
        from v6.registry.model_registry import ModelRegistry

        registry = ModelRegistry()
        router = TradeModeRouter(registry=registry)
        assert router.registry is registry


class TestRuntimeRouterRegistry:
    def test_get_router_creates_on_demand(self):
        from runtime.runtime.runtime_router import RuntimeRouterRegistry

        reg = RuntimeRouterRegistry()
        router = reg.get_router("scan")
        assert router is not None
        assert router in reg._routers.values()

    def test_get_router_returns_same_instance(self):
        from runtime.runtime.runtime_router import RuntimeRouterRegistry

        reg = RuntimeRouterRegistry()
        r1 = reg.get_router("scan")
        r2 = reg.get_router("scan")
        assert r1 is r2

    def test_different_contexts_different_routers(self):
        from runtime.runtime.runtime_router import RuntimeRouterRegistry

        reg = RuntimeRouterRegistry()
        r1 = reg.get_router("scan")
        r2 = reg.get_router("inference")
        assert r1 is not r2

    def test_register_custom_router(self):
        from runtime.runtime.runtime_router import RuntimeRouterRegistry, TradeModeRouter

        reg = RuntimeRouterRegistry()
        custom = TradeModeRouter()
        reg.register_router("custom", custom)
        assert reg.get_router("custom") is custom

    def test_default_context(self):
        from runtime.runtime.runtime_router import RuntimeRouterRegistry

        reg = RuntimeRouterRegistry()
        router = reg.get_router()
        assert router is not None
        assert "default" in reg._routers


class TestSharedRuntimeRouter:
    def test_get_shared_returns_singleton(self):
        from runtime.runtime.runtime_router import get_shared_runtime_router
        import runtime.runtime.runtime_router as mod

        # Reset singleton
        mod._SHARED_ROUTER = None

        r1 = get_shared_runtime_router()
        r2 = get_shared_runtime_router()
        assert r1 is r2

    def test_singleton_is_trade_mode_router(self):
        from runtime.runtime.runtime_router import TradeModeRouter, get_shared_runtime_router
        import runtime.runtime.runtime_router as mod

        mod._SHARED_ROUTER = None
        router = get_shared_runtime_router()
        assert isinstance(router, TradeModeRouter)


class TestRoutedExecutionTarget:
    def test_dataclass_construction(self):
        from runtime.runtime.runtime_router import RoutedExecutionTarget
        from v6.contracts.enums import TradeMode

        target = RoutedExecutionTarget(
            trade_mode=TradeMode.SWING,
            champion=None,
            engine_name="test_engine",
            engine_version="1.0.0",
            is_fallback=False,
        )
        assert target.trade_mode == TradeMode.SWING
        assert target.engine_name == "test_engine"
        assert target.is_fallback is False

    def test_dataclass_with_fallback(self):
        from runtime.runtime.runtime_router import RoutedExecutionTarget
        from v6.contracts.enums import TradeMode

        target = RoutedExecutionTarget(
            trade_mode=TradeMode.AGGRESSIVE_SCALP,
            champion=None,
            engine_name="fallback_engine",
            engine_version="0.5.0",
            is_fallback=True,
            fallback_reason="No champion for mode",
        )
        assert target.is_fallback is True
        assert target.fallback_reason == "No champion for mode"


class TestTradeModeRouterDefaultInit:
    def test_creates_default_registry_when_none_provided(self):
        from runtime.runtime.runtime_router import TradeModeRouter

        router = TradeModeRouter()
        assert router._registry is not None

    def test_accepts_custom_registry(self):
        from runtime.runtime.runtime_router import TradeModeRouter
        from v6.registry.model_registry import ModelRegistry

        registry = ModelRegistry()
        router = TradeModeRouter(registry=registry)
        assert router._registry is registry
