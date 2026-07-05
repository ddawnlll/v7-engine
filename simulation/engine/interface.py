"""
SimulationEngine interface — contract for all simulation adapters.

Defines:
  - SimulationEngine (ABC): abstract base with run, validate_input, validate_output
  - AdapterRegistry: kind-based registration and lookup
  - SideEffectFreeCheck: decorator/context manager that verifies no file mutation occurs

Every adapter in simulation/adapters/ implements SimulationEngine so the runtime
can dispatch by kind without knowing internal details.
"""

from __future__ import annotations

import os
import hashlib
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from typing import Callable, Iterator, Optional

from simulation.contracts.models import SimulationInput, SimulationOutput


# ── Standard adapter kinds ──────────────────────────────────────────────

ADAPTER_KIND_TRAINING = "TRAINING"
ADAPTER_KIND_EVALUATION = "EVALUATION"
ADAPTER_KIND_PAPER = "PAPER"
ADAPTER_KIND_REPLAY = "REPLAY"
ADAPTER_KIND_MONTE_CARLO = "MONTE_CARLO"

STANDARD_ADAPTER_KINDS: frozenset[str] = frozenset({
    ADAPTER_KIND_TRAINING,
    ADAPTER_KIND_EVALUATION,
    ADAPTER_KIND_PAPER,
    ADAPTER_KIND_REPLAY,
    ADAPTER_KIND_MONTE_CARLO,
})


# ── SimulationEngine abstract base ──────────────────────────────────────


class SimulationEngine(ABC):
    """Abstract base for simulation adapters.

    Every adapter wraps ``simulation.engine.engine.simulate()`` with a fixed
    ``adapter_kind`` in the output lineage, plus input/output validation.

    Implementations MUST be side-effect-free: identical input always produces
    identical output (modulo the UUID ``simulation_run_id``).
    """

    @abstractmethod
    def run(self, input: SimulationInput) -> SimulationOutput:
        """Execute simulation and return comparative outcomes.

        Args:
            input: Fully-populated SimulationInput.

        Returns:
            SimulationOutput with adapter_kind set in lineage.
        """
        ...

    @abstractmethod
    def get_adapter_kind(self) -> str:
        """Return the adapter kind string (e.g. 'TRAINING', 'PAPER').

        Must match one of the STANDARD_ADAPTER_KINDS.
        """
        ...

    def validate_input(self, input: SimulationInput) -> list[str]:
        """Validate a SimulationInput before execution.

        Returns a list of error messages (empty = valid).
        Override in subclasses to add adapter-specific checks.
        """
        errors: list[str] = []
        if not input.symbol or not input.symbol.strip():
            errors.append("symbol must be non-empty")
        if input.entry_price <= 0:
            errors.append(f"entry_price must be positive, got {input.entry_price}")
        if input.atr <= 0:
            errors.append(f"atr must be positive, got {input.atr}")
        if not input.future_path or not input.future_path.candles:
            errors.append("future_path must contain at least one candle")
        if not input.profile:
            errors.append("profile is required")
        if input.profile and input.profile.stop_multiplier <= 0:
            errors.append(f"stop_multiplier must be positive, got {input.profile.stop_multiplier}")
        if input.profile and input.profile.target_multiplier <= 0:
            errors.append(
                f"target_multiplier must be positive, got {input.profile.target_multiplier}"
            )
        return errors

    def validate_output(self, output: SimulationOutput) -> list[str]:
        """Validate a SimulationOutput after execution.

        Returns a list of error messages (empty = valid).
        Override in subclasses to add adapter-specific checks.
        """
        errors: list[str] = []
        if not output.simulation_run_id:
            errors.append("simulation_run_id must be non-empty")
        if not output.symbol:
            errors.append("symbol must be non-empty")
        if output.resolution_status not in ("COMPLETE", "UNRESOLVED", "INVALIDATED"):
            errors.append(
                f"invalid resolution_status '{output.resolution_status}'; "
                f"expected COMPLETE, UNRESOLVED, or INVALIDATED"
            )
        valid_actions = {"LONG_NOW", "SHORT_NOW", "NO_TRADE", "AMBIGUOUS_STATE"}
        if output.best_action not in valid_actions:
            errors.append(
                f"invalid best_action '{output.best_action}'; "
                f"expected one of {valid_actions}"
            )
        if output.long_outcome is None:
            errors.append("long_outcome must not be None")
        if output.short_outcome is None:
            errors.append("short_outcome must not be None")
        if output.no_trade_outcome is None:
            errors.append("no_trade_outcome must not be None")
        if not output.lineage.adapter_kind:
            errors.append("lineage.adapter_kind must be non-empty")
        return errors

    def is_side_effect_free(self) -> bool:
        """Return True if the adapter guarantees no side effects.

        Side-effect-free means: no network I/O, no file writes, no
        external state mutation, no exchange API calls. All adapters
        in this project honour this guarantee.
        """
        return True


# ── AdapterRegistry ─────────────────────────────────────────────────────


class AdapterRegistryError(Exception):
    """Raised on invalid adapter registration or lookup."""


class AdapterRegistry:
    """Kind-based registry for SimulationEngine implementations.

    Usage::

        registry = AdapterRegistry()
        registry.register("TRAINING", training_engine)
        engine = registry.get("TRAINING")
        assert registry.list_adapters() == ["TRAINING"]
    """

    def __init__(self) -> None:
        self._engines: dict[str, SimulationEngine] = {}

    def register(self, kind: str, engine: SimulationEngine) -> None:
        """Register an engine under *kind*.

        Raises ``AdapterRegistryError`` if *kind* is already registered or
        *engine* is not a ``SimulationEngine`` instance.
        """
        if kind in self._engines:
            raise AdapterRegistryError(
                f"adapter kind '{kind}' is already registered"
            )
        if not isinstance(engine, SimulationEngine):
            raise AdapterRegistryError(
                f"engine must be a SimulationEngine instance, got {type(engine).__name__}"
            )
        if kind not in STANDARD_ADAPTER_KINDS:
            raise AdapterRegistryError(
                f"adapter kind '{kind}' is not a standard kind; "
                f"expected one of {sorted(STANDARD_ADAPTER_KINDS)}"
            )
        self._engines[kind] = engine

    def get(self, kind: str) -> SimulationEngine:
        """Retrieve the engine registered under *kind*.

        Raises ``AdapterRegistryError`` if *kind* is not registered.
        """
        engine = self._engines.get(kind)
        if engine is None:
            raise AdapterRegistryError(
                f"no adapter registered for kind '{kind}'; "
                f"registered kinds: {sorted(self._engines)}"
            )
        return engine

    def list_adapters(self) -> list[str]:
        """Return sorted list of registered adapter kinds."""
        return sorted(self._engines)

    def __len__(self) -> int:
        return len(self._engines)

    def __contains__(self, kind: str) -> bool:
        return kind in self._engines


# ── SideEffectFreeCheck ─────────────────────────────────────────────────


@dataclass(frozen=True)
class _FileSnapshot:
    """Hash + mtime for a single file."""
    path: str
    mtime_ns: int
    size: int
    sha256_prefix: str  # first 16 hex chars of SHA-256


def _take_snapshot(root_dir: str) -> dict[str, _FileSnapshot]:
    """Walk *root_dir* and record every .py file's metadata."""
    snap: dict[str, _FileSnapshot] = {}
    root_dir = os.path.abspath(root_dir)
    for dirpath, _dirnames, filenames in os.walk(root_dir):
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dirpath, fn)
            try:
                stat = os.stat(full)
            except OSError:
                continue
            # Only first 16 hex chars of SHA-256 — fast approximate check
            try:
                with open(full, "rb") as f:
                    content = f.read(65536)  # read up to 64KB
                h = hashlib.sha256(content).hexdigest()[:16]
            except OSError:
                h = ""
            snap[full] = _FileSnapshot(
                path=full,
                mtime_ns=stat.st_mtime_ns,
                size=stat.st_size,
                sha256_prefix=h,
            )
    return snap


def _diff_snapshots(
    before: dict[str, _FileSnapshot],
    after: dict[str, _FileSnapshot],
) -> list[str]:
    """Return human-readable change descriptions."""
    changes: list[str] = []
    # Check for modifications / deletions
    for path, b in before.items():
        a = after.get(path)
        if a is None:
            changes.append(f"DELETED: {path}")
        elif a.mtime_ns != b.mtime_ns or a.size != b.size:
            changes.append(f"MODIFIED: {path}")
        elif a.sha256_prefix != b.sha256_prefix:
            changes.append(f"MODIFIED (content only): {path}")
    # Check for new files
    for path in after:
        if path not in before:
            changes.append(f"CREATED: {path}")
    return changes


class SideEffectFreeCheck:
    """Decorator and context manager that verifies no file mutation occurs.

    Checks that no ``.py`` files are created, modified, or deleted within
    the watched directory tree during execution.

    Usage as context manager::

        with SideEffectFreeCheck():
            engine.run(sim_input)

    Usage as decorator::

        @SideEffectFreeCheck()
        def safe_simulate(input: SimulationInput) -> SimulationOutput:
            return simulate(input)
    """

    _WATCH_DIR: str = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )

    def __init__(self, watch_dir: str | None = None) -> None:
        self._watch_dir = os.path.abspath(
            watch_dir or self._WATCH_DIR
        )
        self._before: dict[str, _FileSnapshot] = {}

    # -- context manager protocol -----------------------------------------

    def __enter__(self) -> SideEffectFreeCheck:
        self._before = _take_snapshot(self._watch_dir)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        if exc_type is not None:
            return  # function already raised — don't mask with our check
        after = _take_snapshot(self._watch_dir)
        changes = _diff_snapshots(self._before, after)
        if changes:
            raise RuntimeError(
                f"Side-effect-free violation in {self._watch_dir}:\n"
                + "\n".join(f"  {c}" for c in changes)
            )

    # -- decorator protocol -----------------------------------------------

    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: object, **kwargs: object) -> object:
            before = _take_snapshot(self._watch_dir)
            try:
                result = func(*args, **kwargs)
            except BaseException:
                raise
            after = _take_snapshot(self._watch_dir)
            changes = _diff_snapshots(before, after)
            if changes:
                raise RuntimeError(
                    f"Side-effect-free violation in {func.__name__}:\n"
                    + "\n".join(f"  {c}" for c in changes)
                )
            return result
        return wrapper
