"""Minimal V6 config stub for V7 runtime compatibility."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Phase8Config:
    circuit_breaker_timeout_trip_count: int = 3
    circuit_breaker_schema_failure_trip_count: int = 3
    circuit_breaker_hard_block_trip_count: int = 5
    metrics_recent_scan_limit: int = 100


@dataclass
class Phase7ApiConfig:
    enabled: bool = True


@dataclass
class V6Config:
    phase8: Phase8Config = field(default_factory=Phase8Config)
    phase7_api: Phase7ApiConfig = field(default_factory=Phase7ApiConfig)

    @classmethod
    def load(cls, path: Path) -> V6Config:
        return cls()

    @classmethod
    def defaults(cls) -> V6Config:
        return cls()
