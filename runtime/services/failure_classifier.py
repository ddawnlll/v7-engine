"""Structured failure classification for losing paper trades."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any

import httpx


FAILURE_SOURCES = {
    "SIGNAL_QUALITY",
    "TIMING",
    "RISK_MODEL",
    "THRESHOLD_LOGIC",
    "MARKET_CONDITION",
}
BLAMED_COMPONENTS = {
    "RSI",
    "MACD",
    "Volume",
    "Trend Filter",
    "Entry Logic",
    "Stop Loss",
    "Take Profit",
}
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-20250514"


@dataclass(slots=True)
class FailureRecord:
    order_id: str
    signal_id: str | None
    failure_source: str
    blamed_component: str
    severity_score: int
    confidence: float
    classification: str
    explanation: str
    improvement: str
    created_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FailureClassifier:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL
        self.http_client = http_client

    def classify(
        self,
        *,
        order: dict[str, Any],
        signal: dict[str, Any] | None,
        snapshot: dict[str, Any] | None,
        realized_r: float | None,
        created_at_utc: str,
    ) -> FailureRecord:
        payload = self._build_prompt_payload(order=order, signal=signal, snapshot=snapshot, realized_r=realized_r)
        if self.api_key:
            record = self._classify_with_anthropic(payload, created_at_utc=created_at_utc)
            if record is not None:
                try:
                    return self._validate_record(record, order_id=str(order.get("order_id") or ""), signal_id=order.get("signal_id"), created_at_utc=created_at_utc)
                except Exception:
                    pass
        return self._heuristic_classification(order=order, signal=signal, snapshot=snapshot, realized_r=realized_r, created_at_utc=created_at_utc)

    def _classify_with_anthropic(self, payload: dict[str, Any], *, created_at_utc: str) -> dict[str, Any] | None:
        headers = {
            "x-api-key": str(self.api_key),
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": 300,
            "temperature": 0,
            "system": (
                "You are a trade failure classifier. "
                "Return JSON only. "
                "Use only the allowed enums for failure_source and blamed_component. "
                "Keep explanation technical and at most two sentences."
            ),
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "Classify why this losing trade failed.",
                            "allowed_failure_sources": sorted(FAILURE_SOURCES),
                            "allowed_blamed_components": sorted(BLAMED_COMPONENTS),
                            "required_fields": [
                                "failure_source",
                                "blamed_component",
                                "severity_score",
                                "confidence",
                                "classification",
                                "explanation",
                                "improvement",
                            ],
                            "trade": payload,
                        }
                    ),
                }
            ],
        }
        client = self.http_client or httpx.Client(timeout=10.0)
        close_client = self.http_client is None
        try:
            response = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
        except Exception:
            return None
        finally:
            if close_client:
                client.close()

        text_chunks: list[str] = []
        for block in data.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                text_chunks.append(str(block["text"]))
        if not text_chunks:
            return None
        return self._extract_json_record("\n".join(text_chunks))

    @staticmethod
    def _extract_json_record(raw_text: str) -> dict[str, Any] | None:
        try:
            return json.loads(raw_text)
        except Exception:
            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if not match:
                return None
            try:
                return json.loads(match.group(0))
            except Exception:
                return None

    def _heuristic_classification(
        self,
        *,
        order: dict[str, Any],
        signal: dict[str, Any] | None,
        snapshot: dict[str, Any] | None,
        realized_r: float | None,
        created_at_utc: str,
    ) -> FailureRecord:
        signal_payload = signal or {}
        snapshot_payload = snapshot or {}
        audit = dict(signal_payload.get("audit") or {})
        decision_path = dict((audit.get("decision_path") or {}))
        stop_model = dict(audit.get("stop_model") or {})
        direction = str(order.get("direction") or signal_payload.get("direction") or "").upper()
        close_reason = str(order.get("close_reason") or order.get("payload", {}).get("close_reason") or "").upper()
        confidence = max(0.0, min(1.0, float(signal_payload.get("confidence") or order.get("confidence") or 0.0) / 100.0))
        trend = str(signal_payload.get("trend") or snapshot_payload.get("trend") or "")
        regime = str(signal_payload.get("regime") or snapshot_payload.get("regime") or "")

        if close_reason == "HIT_SL":
            breakdown = dict(decision_path.get("entry_quality_breakdown") or {})
            stop_distance_atr = float(stop_model.get("stop_distance_atr") or 0.0)
            if any(key in breakdown for key in {"ema_extension", "impulse_decay_macd", "impulse_decay_rsi", "worst_bucket_guardrail"}):
                failure_source = "TIMING"
                blamed_component = "Entry Logic"
                classification = "ENTRY_TOO_LATE"
                explanation = "The stop was reached after a stretched or decelerating entry. Timing quality failed before the broader thesis could resolve."
                improvement = "Require breakout-hold or retest confirmation before entering extended trend continuation."
            elif stop_model.get("stop_method") == "atr_floor" or (0.0 < stop_distance_atr < 1.1):
                failure_source = "RISK_MODEL"
                blamed_component = "Stop Loss"
                classification = "STOP_TOO_TIGHT"
                explanation = "The stop relied on a narrow volatility floor rather than a structural anchor. Local path noise invalidated the trade first."
                improvement = "Anchor stops beyond structure or sweep zones and re-check reward geometry after widening."
            elif regime in {"HIGH_VOL", "MOMENTUM"}:
                failure_source = "MARKET_CONDITION"
                blamed_component = "Stop Loss"
                classification = "REGIME_MISMATCH"
                explanation = "The trade was stopped in a hostile regime where continuation conditions were unstable. Environment mismatch dominated outcome quality."
                improvement = "Block or heavily penalize that regime before entry unless structure is exceptional."
            else:
                failure_source = "RISK_MODEL"
                blamed_component = "Stop Loss"
                classification = "STOP_STRUCTURALLY_WRONG"
                explanation = "The stop placement did not line up with the nearest meaningful structure. The market reached the stop before invalidating the broader idea."
                improvement = "Place the stop beyond the relevant structural anchor instead of an exposed intermediate level."
        elif close_reason in {"TIME_STOP", "EARLY_STALE_EXIT"}:
            failure_source = "TIMING"
            blamed_component = "Entry Logic"
            if close_reason == "EARLY_STALE_EXIT":
                classification = "EARLY_STALE_EXIT"
                explanation = "The trade failed to show enough directional development early in its holding window. Capital was cut before the full time stop to avoid stale occupancy."
                improvement = "Tighten entry urgency filters and condition duration targets by regime and session."
            elif realized_r is not None and realized_r <= -0.4:
                classification = "LATE_REVERSAL"
                explanation = "The trade never developed and then reversed before target. The time stop reflects weak follow-through quality."
                improvement = "Tighten entry confirmation when momentum is already decelerating at the trigger."
            elif realized_r is not None and abs(realized_r) <= 0.2:
                classification = "STALE_RANGE_HOLD"
                explanation = "The trade spent its holding window moving sideways without meaningful expansion. The setup lacked urgency."
                improvement = "Reduce participation in stale range-bound conditions and demand clearer expansion signatures."
            elif realized_r is not None and realized_r < 0:
                classification = "SLOW_DRIFT"
                explanation = "The trade decayed slowly rather than failing instantly. Entry timing and session quality did not produce sufficient continuation."
                improvement = "Require stronger confirmation or avoid low-energy session/regime combinations."
            else:
                classification = "NEVER_DEVELOPED"
                explanation = "The setup failed to move within the expected holding window. Entry timing lagged the actionable impulse."
                improvement = "Delay entry until confirmation survives one additional candle in the same direction."
        elif close_reason == "MANUAL_CLOSE":
            failure_source = "THRESHOLD_LOGIC"
            blamed_component = "Take Profit"
            classification = "MANUAL_INVALIDATION"
            explanation = "The trade was closed before the planned exit logic completed. Exit management overrode the original threshold model."
            improvement = "Tighten manual override criteria so only structural invalidation interrupts the planned exit."
        elif direction == "BUY" and trend == "BEARISH" or direction == "SELL" and trend == "BULLISH":
            failure_source = "SIGNAL_QUALITY"
            blamed_component = "Trend Filter"
            classification = "WRONG_DIRECTION"
            explanation = "The trade direction opposed the prevailing trend state. The directional filter admitted a low-alignment setup."
            improvement = "Require stronger trend alignment before allowing counter-trend entries."
        elif regime in {"SQUEEZE", "DEAD"}:
            failure_source = "MARKET_CONDITION"
            blamed_component = "Volume"
            classification = "LOW_PARTICIPATION"
            explanation = "The loss occurred in a weak participation regime with poor expansion follow-through. Market conditions did not support the expected move."
            improvement = "Raise minimum liquidity and expansion requirements before entering in low-energy regimes."
        else:
            failure_source = "SIGNAL_QUALITY"
            blamed_component = "MACD"
            classification = "WEAK_CONFIRMATION"
            explanation = "Momentum confirmation was insufficient for the realized move path. The setup quality was weaker than the final confidence implied."
            improvement = "Increase confirmation requirements when momentum and structure disagree."

        if realized_r is not None and realized_r <= -2.0:
            severity = 5
        elif realized_r is not None and realized_r <= -1.5:
            severity = 4
        elif realized_r is not None and realized_r <= -1.0:
            severity = 3
        else:
            severity = 2

        return FailureRecord(
            order_id=str(order.get("order_id") or ""),
            signal_id=str(order.get("signal_id")) if order.get("signal_id") else None,
            failure_source=failure_source,
            blamed_component=blamed_component,
            severity_score=severity,
            confidence=max(confidence, 0.61),
            classification=classification,
            explanation=explanation,
            improvement=improvement,
            created_at_utc=created_at_utc,
        )

    @staticmethod
    def _build_prompt_payload(
        *,
        order: dict[str, Any],
        signal: dict[str, Any] | None,
        snapshot: dict[str, Any] | None,
        realized_r: float | None,
    ) -> dict[str, Any]:
        signal_payload = signal or {}
        return {
            "order_id": order.get("order_id"),
            "signal_id": order.get("signal_id"),
            "symbol": order.get("symbol"),
            "interval": order.get("interval"),
            "mode": order.get("mode"),
            "direction": order.get("direction"),
            "close_reason": order.get("close_reason") or order.get("payload", {}).get("close_reason"),
            "entry": order.get("entry"),
            "stop_loss": order.get("stop_loss"),
            "take_profit": order.get("take_profit"),
            "close_price": order.get("close_price"),
            "confidence": order.get("confidence"),
            "realized_r": realized_r,
            "signal_summary": signal_payload.get("summary"),
            "signal_regime": signal_payload.get("regime"),
            "signal_trend": signal_payload.get("trend"),
            "signal_factors": signal_payload.get("factors"),
            "snapshot": snapshot or {},
        }

    def _validate_record(
        self,
        payload: dict[str, Any],
        *,
        order_id: str,
        signal_id: str | None,
        created_at_utc: str,
    ) -> FailureRecord:
        failure_source = str(payload.get("failure_source") or "").strip().upper()
        if failure_source not in FAILURE_SOURCES:
            raise ValueError(f"Invalid failure_source: {failure_source}")

        blamed_component = str(payload.get("blamed_component") or "").strip()
        if blamed_component not in BLAMED_COMPONENTS:
            raise ValueError(f"Invalid blamed_component: {blamed_component}")

        severity_score = int(max(1, min(5, int(payload.get("severity_score") or 1))))
        confidence = max(0.0, min(1.0, float(payload.get("confidence") or 0.0)))
        classification = self._normalize_label(str(payload.get("classification") or "UNCLASSIFIED"))
        explanation = self._limit_to_two_sentences(str(payload.get("explanation") or "Failure classification unavailable."))
        improvement = " ".join(str(payload.get("improvement") or "Review the setup and tighten the failing rule.").split())[:240]

        return FailureRecord(
            order_id=order_id,
            signal_id=signal_id,
            failure_source=failure_source,
            blamed_component=blamed_component,
            severity_score=severity_score,
            confidence=confidence,
            classification=classification,
            explanation=explanation,
            improvement=improvement,
            created_at_utc=created_at_utc,
        )

    @staticmethod
    def _normalize_label(value: str) -> str:
        cleaned = re.sub(r"[^A-Z0-9_]+", "_", value.strip().upper()).strip("_")
        return cleaned or "UNCLASSIFIED"

    @staticmethod
    def _limit_to_two_sentences(value: str) -> str:
        normalized = " ".join(value.split())
        parts = re.split(r"(?<=[.!?])\s+", normalized)
        filtered = [part.strip() for part in parts if part.strip()]
        if not filtered:
            return "Failure classification unavailable."
        return " ".join(filtered[:2])
