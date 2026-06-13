"""Internal registry for contract-compatible analyzer engines."""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from runtime.db.repos.settings_repo import SettingsRepository
from runtime.db.session import session_scope
from runtime.services.analyzer_engine_contract import AnalyzerEngineDefinition, RESPONSE_SCHEMA_VERSION

logger = logging.getLogger(__name__)


@runtime_checkable
class AnalyzerEngine(Protocol):
    name: str
    version: str
    is_fallback: bool

    def analyze(self, request): ...
    def health_check(self) -> bool: ...


class UnavailableAnalyzerEngine:
    def __init__(self, name: str, version: str, reason: str, *, is_fallback: bool = False) -> None:
        self.name = name
        self.version = version
        self.is_fallback = is_fallback
        self.reason = reason

    def health_check(self) -> bool:
        return False

    def analyze(self, request):
        raise RuntimeError(f"Analyzer engine {self.name} is unavailable: {self.reason}")


class AnalyzerEngineRegistryService:
    def __init__(self, settings_repo: SettingsRepository | None = None) -> None:
        self.settings_repo = settings_repo or SettingsRepository()
        self._instances: dict[str, AnalyzerEngine] = {}
        self._fallback_engine_name: str | None = None
        self._register_defaults()

    def _register_defaults(self) -> None:
        try:
            from static_engine.v4_analyzer_engine import V4AnalyzerEngine

            self.register(V4AnalyzerEngine())
        except ModuleNotFoundError as exc:
            if exc.name != "lancedb":
                raise
            logger.warning("v4 engine optional dependency unavailable: %s", exc)
            self.register(UnavailableAnalyzerEngine("v4_default", "unavailable", str(exc), is_fallback=True))
        try:
            from v5.engine.analyzer_engine import V5AnalyzerEngine

            self.register(V5AnalyzerEngine())
        except ModuleNotFoundError as exc:
            if exc.name not in {"lancedb", "lightgbm"}:
                raise
            logger.warning("v5 engine optional dependency unavailable: %s", exc)
            self.register(UnavailableAnalyzerEngine("v5", "unavailable", str(exc)))
        except Exception as exc:
            logger.warning("v5 engine registration failed: %s", exc)

    def register(self, engine: AnalyzerEngine) -> None:
        if not isinstance(engine, AnalyzerEngine):
            raise TypeError(f"Engine does not satisfy AnalyzerEngine protocol: {engine!r}")
        self._instances[engine.name] = engine
        if engine.is_fallback or self._fallback_engine_name is None:
            self._fallback_engine_name = engine.name

    def list_engines(self) -> list[dict]:
        active_name = self.active_engine_name()
        items = []
        for engine in self._instances.values():
            status = "ACTIVE" if engine.name == active_name else "EXPERIMENTAL"
            description = "Registered analyzer engine."
            if engine.name == "v4_default":
                description = "Current in-process v4 analyzer extracted behind the Phase 25 contract."
            elif engine.name == "v5":
                description = "Experimental v5 decision-correction engine behind the Phase 25 contract."
            items.append(
                AnalyzerEngineDefinition(
                    engine_name=engine.name,
                    engine_version=engine.version,
                    status=status,
                    schema_version=RESPONSE_SCHEMA_VERSION,
                    enabled=bool(engine.health_check()),
                    description=description,
                ).model_dump()
            )
        return items

    def list_engines_raw(self) -> list[dict]:
        return self.list_engines()

    def active_engine_name(self) -> str:
        with session_scope() as session:
            settings = self.settings_repo.get_all(session)
        requested = str(settings.get("ANALYZER_ACTIVE_ENGINE") or self._fallback_engine_name or "v4_default").strip()
        if requested in self._instances:
            return requested
        return self._fallback_engine_name or "v4_default"

    def shadow_engine_name(self) -> str | None:
        """Returns the configured shadow engine if valid, or None."""
        with session_scope() as session:
            settings = self.settings_repo.get_all(session)
        requested = settings.get("SHADOW_ENGINE")
        if requested and str(requested).strip() in self._instances:
            return str(requested).strip()
        return None

    def get_engine(self, engine_name: str | None = None):
        selected = str(engine_name or self.active_engine_name() or self._fallback_engine_name or "v4_default")
        return self._instances.get(selected) or self._instances[self._fallback_engine_name or "v4_default"]
