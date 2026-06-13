"""Standard analyzer engine request and response contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


REQUEST_SCHEMA_VERSION = "analysis_request.v1"
RESPONSE_SCHEMA_VERSION = "analysis_result.v1"


class AnalysisRequest(BaseModel):
    schema_version: str = Field(default=REQUEST_SCHEMA_VERSION)
    request_id: str
    symbol: str
    interval: str
    mode: str
    timestamp: str
    snapshot: dict[str, Any]
    market_context: dict[str, Any] = Field(default_factory=dict)
    runtime_context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol", "interval", "mode", "timestamp", "request_id")
    @classmethod
    def _required_text(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("field is required")
        return text

    @field_validator("snapshot")
    @classmethod
    def _snapshot_required(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict) or not value:
            raise ValueError("snapshot is required")
        return value


class AnalysisResult(BaseModel):
    schema_version: str = Field(default=RESPONSE_SCHEMA_VERSION)
    signal_status: Literal["SIGNAL", "NEUTRAL", "REJECTED", "DEGRADED", "ERROR", "FILTERED"]
    direction: str
    confidence: float = 0.0
    probability: float = 0.0
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_reward: float | None = None
    summary: str = ""
    engine_name: str
    engine_version: str
    analysis_latency_ms: float = 0.0
    fallback_used: bool = False
    fallback_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    corrected_probability: float | None = None
    recommended_action: str | None = None
    reason_summary: str | None = None
    retrieval_summary: dict[str, Any] = Field(default_factory=dict)
    model_version: str | None = None
    memory_used: bool = False
    static_engine_raw_confidence: float | None = None
    gate_owner: str | None = None
    gate_decision: str | None = None
    confidence_gap: float | None = None
    decision_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("engine_name", "engine_version", "direction", "summary")
    @classmethod
    def _normalize_text(cls, value: str) -> str:
        return str(value or "").strip()


class AnalyzerEngineDefinition(BaseModel):
    engine_name: str
    engine_version: str
    status: Literal["ACTIVE", "DISABLED", "EXPERIMENTAL"]
    schema_version: str = Field(default=RESPONSE_SCHEMA_VERSION)
    enabled: bool = True
    description: str = ""
