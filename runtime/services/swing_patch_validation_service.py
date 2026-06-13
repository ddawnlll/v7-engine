"""Post-patch swing validation against the known bad diagnostic baseline."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from typing import Any

from runtime.db.session import session_scope
from runtime.services.trade_analytics_service import TradeAnalyticsService, _as_float

BAD_BASELINE_ID = "swing_patch_bad_2026_04_02"
BAD_BASELINE = {
    "baseline_id": BAD_BASELINE_ID,
    "captured_at": "2026-04-02T00:00:00+00:00",
    "sample_notes": [
        "8 swing stop-outs, all full -1R losses.",
        "Stop failures split into 6 STOP_TOO_TIGHT and 2 STOP_STRUCTURALLY_WRONG.",
        "12 of 28 swings closed via EARLY_STALE_EXIT.",
        "HIGH_VOL swing win rate collapsed to 22%.",
        "TRENDING swing win rate collapsed to 12.5%.",
        "70-80 confidence bucket realized roughly 30% win rate against ~75% expected.",
    ],
    "stops": {
        "stop_too_tight_pct": 0.75,
        "stop_structurally_wrong_pct": 0.25,
    },
    "stale_exits": {
        "swing_early_stale_exit_count": 12,
        "swing_1h_plus_early_stale_exit_count": 12,
    },
    "regimes": {
        "win_rates": {
            "HIGH_VOL": 0.22,
            "TRENDING": 0.125,
            "RANGING": 0.625,
        },
    },
    "confidence": {
        "bucket_70_80_actual_win_rate": 0.30,
        "bucket_70_80_expected_win_rate": 0.75,
        "bucket_70_80_gap": 0.45,
        "swing_component_penalty_live_impact_count": 1,
    },
}


@dataclass(slots=True)
class ValidationCheck:
    key: str
    passed: bool
    severity: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "passed": self.passed,
            "severity": self.severity,
            "reason": self.reason,
        }


class SwingPatchValidationService:
    def __init__(self, trade_analytics_service: TradeAnalyticsService | None = None) -> None:
        self.trade_analytics_service = trade_analytics_service or TradeAnalyticsService()

    def get_validation_payload(self, *, lookback_days: int = 30, interval_min_minutes: int = 60) -> dict[str, Any]:
        with session_scope() as session:
            rows = self.trade_analytics_service._base_rows(
                session,
                lookback_days=lookback_days,
                filters={"mode": "SWING", "symbol": None, "interval": None, "direction": None},
            )
        current = self.trade_analytics_service._current_window(rows, lookback_days=lookback_days)
        swing_rows = [row for row in current if str(row.get("mode") or "").upper() == "SWING"]
        hour_plus_rows = [row for row in swing_rows if _as_float(row.get("interval_minutes")) >= float(interval_min_minutes)]
        stop_rows = [row for row in swing_rows if bool(row.get("stop_hit"))]
        stale_rows = [row for row in swing_rows if bool(row.get("stale_exit"))]
        stale_hour_plus_rows = [row for row in hour_plus_rows if bool(row.get("stale_exit"))]
        time_stop_rows = [row for row in swing_rows if bool(row.get("time_exit"))]
        component_penalty_live_impact_count = sum(
            1
            for row in swing_rows
            if row.get("component_penalty_multiplier") is not None and _as_float(row.get("component_penalty_multiplier"), 1.0) < 1.0
        )

        stop_too_tight_count = sum(1 for row in stop_rows if str(row.get("failure_classification") or "") == "STOP_TOO_TIGHT")
        stop_structurally_wrong_count = sum(1 for row in stop_rows if str(row.get("failure_classification") or "") == "STOP_STRUCTURALLY_WRONG")
        avg_stop_distance_atr = self._avg([_as_float(row.get("stop_distance_atr")) for row in stop_rows if row.get("stop_distance_atr") is not None])
        avg_structure_gap_atr = self._avg_structure_gap_atr(stop_rows)

        regime_counts = self._count_by(swing_rows, "regime")
        regime_win_rates = self._win_rate_by(swing_rows, "regime")
        distribution_shift_ok = self._distribution_shift_ok(regime_counts)

        bucket_rows = self.trade_analytics_service.get_confidence_bucket_breakdown_from_rows(swing_rows)
        calibration_gap = self._overall_bucket_gap(bucket_rows)
        bucket_70_80 = next((row for row in bucket_rows if str(row.get("label")) == "70-80"), None)
        bucket_70_80_gap = None
        if bucket_70_80 is not None:
            bucket_70_80_gap = abs((_as_float(bucket_70_80.get("avg_calibrated_confidence")) / 100.0) - _as_float(bucket_70_80.get("win_rate")))

        accepted_before = sum(1 for row in swing_rows if _as_float(row.get("confidence_before_learning")) >= 25.0)
        accepted_after = sum(1 for row in swing_rows if _as_float(row.get("confidence_after_learning") or row.get("confidence")) >= 25.0)
        low_confidence_rows = [row for row in swing_rows if _as_float(row.get("confidence_after_learning") or row.get("confidence")) < 35.0]
        low_confidence_flood_flag = len(low_confidence_rows) >= max(5, int(len(swing_rows) * 0.35)) and self._avg([_as_float(row.get("realized_r")) for row in low_confidence_rows]) < 0.0

        hard_checks = [
            ValidationCheck(
                key="swing_1h_early_stale_exit_zero",
                passed=len(stale_hour_plus_rows) == 0,
                severity="hard",
                reason="Hourly+ swing trades must not close via EARLY_STALE_EXIT.",
            ),
            ValidationCheck(
                key="swing_component_penalty_live_impact_zero",
                passed=component_penalty_live_impact_count == 0,
                severity="hard",
                reason="Swing signals must not persist an applied component_penalty multiplier below 1.0.",
            ),
        ]
        stop_share_sample_ready = len(stop_rows) >= 4

        soft_checks = [
            ValidationCheck(
                key="stop_too_tight_down_vs_bad_baseline",
                passed=(not stop_share_sample_ready) or ((stop_too_tight_count / len(stop_rows) if stop_rows else 0.0) < BAD_BASELINE["stops"]["stop_too_tight_pct"]),
                severity="soft",
                reason="STOP_TOO_TIGHT share should be below the frozen bad baseline once stop-hit sample is large enough.",
            ),
            ValidationCheck(
                key="stop_structurally_wrong_down_vs_bad_baseline",
                passed=(not stop_share_sample_ready) or ((stop_structurally_wrong_count / len(stop_rows) if stop_rows else 0.0) < BAD_BASELINE["stops"]["stop_structurally_wrong_pct"]),
                severity="soft",
                reason="STOP_STRUCTURALLY_WRONG share should be below the frozen bad baseline once stop-hit sample is large enough.",
            ),
            ValidationCheck(
                key="regime_distribution_shift_ok",
                passed=distribution_shift_ok,
                severity="soft",
                reason="TRENDING/HIGH_VOL allocation should no longer match the collapse pattern.",
            ),
            ValidationCheck(
                key="confidence_gap_better_than_bad_baseline",
                passed=(bucket_70_80_gap if bucket_70_80_gap is not None else calibration_gap) < BAD_BASELINE["confidence"]["bucket_70_80_gap"],
                severity="soft",
                reason="Confidence bucket gap should improve versus the bad baseline.",
            ),
            ValidationCheck(
                key="no_low_confidence_flood",
                passed=not low_confidence_flood_flag,
                severity="soft",
                reason="Removing swing component penalties must not create a flood of low-quality swing trades.",
            ),
        ]

        checks = hard_checks + soft_checks
        hard_failed = [item for item in hard_checks if not item.passed]
        soft_failed = [item for item in soft_checks if not item.passed]
        overall_status = "PASS"
        release_recommendation = "SAFE_TO_PAPER_VALIDATE"
        if hard_failed:
            overall_status = "FAIL"
            release_recommendation = "BLOCK_RELEASE"
        elif soft_failed:
            overall_status = "PARTIAL"
            release_recommendation = "PAPER_VALIDATE_ONLY"

        return {
            "ok": True,
            "validator_id": "swing_patch_validation.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "baseline": BAD_BASELINE,
            "run_source": self._run_source_label(swing_rows),
            "sample_size": len(swing_rows),
            "overall_status": overall_status,
            "hard_gates": {item.key: item.passed for item in hard_checks},
            "checks": [item.to_dict() for item in checks],
            "pass_fail_reasons": [item.reason for item in checks if not item.passed],
            "stops": {
                "stop_hit_count": len(stop_rows),
                "stop_too_tight_count": stop_too_tight_count,
                "stop_too_tight_pct": round(stop_too_tight_count / len(stop_rows), 4) if stop_rows else 0.0,
                "stop_structurally_wrong_count": stop_structurally_wrong_count,
                "stop_structurally_wrong_pct": round(stop_structurally_wrong_count / len(stop_rows), 4) if stop_rows else 0.0,
                "avg_stop_distance_atr": round(avg_stop_distance_atr, 4) if avg_stop_distance_atr is not None else None,
                "avg_structure_gap_atr": round(avg_structure_gap_atr, 4) if avg_structure_gap_atr is not None else None,
                "delta_vs_bad_baseline": {
                    "stop_too_tight_pct": round((stop_too_tight_count / len(stop_rows) if stop_rows else 0.0) - BAD_BASELINE["stops"]["stop_too_tight_pct"], 4),
                    "stop_structurally_wrong_pct": round((stop_structurally_wrong_count / len(stop_rows) if stop_rows else 0.0) - BAD_BASELINE["stops"]["stop_structurally_wrong_pct"], 4),
                },
                "pass": not any(item.key.startswith("stop_") and not item.passed for item in soft_checks),
            },
            "stale_exits": {
                "swing_early_stale_exit_count": len(stale_rows),
                "swing_1h_plus_early_stale_exit_count": len(stale_hour_plus_rows),
                "swing_time_stop_count": len(time_stop_rows),
                "delta_vs_bad_baseline": {
                    "swing_early_stale_exit_count": len(stale_rows) - BAD_BASELINE["stale_exits"]["swing_early_stale_exit_count"],
                    "swing_1h_plus_early_stale_exit_count": len(stale_hour_plus_rows) - BAD_BASELINE["stale_exits"]["swing_1h_plus_early_stale_exit_count"],
                },
                "pass": all(item.passed for item in hard_checks if "early_stale_exit" in item.key),
            },
            "regimes": {
                "counts": regime_counts,
                "win_rates": regime_win_rates,
                "distribution_shift_ok": distribution_shift_ok,
                "delta_vs_bad_baseline": {
                    name: round(_as_float(regime_win_rates.get(name)) - _as_float(BAD_BASELINE["regimes"]["win_rates"].get(name)), 4)
                    for name in BAD_BASELINE["regimes"]["win_rates"].keys()
                },
                "pass": next(item.passed for item in soft_checks if item.key == "regime_distribution_shift_ok"),
            },
            "confidence": {
                "accepted_signal_count_before": accepted_before,
                "accepted_signal_count_after": accepted_after,
                "bucket_calibration_gap": round(calibration_gap, 4) if calibration_gap is not None else None,
                "bucket_70_80_gap": round(bucket_70_80_gap, 4) if bucket_70_80_gap is not None else None,
                "component_penalty_affected_count": component_penalty_live_impact_count,
                "low_confidence_flood_flag": low_confidence_flood_flag,
                "delta_vs_bad_baseline": {
                    "bucket_70_80_gap": round((bucket_70_80_gap if bucket_70_80_gap is not None else calibration_gap or 0.0) - BAD_BASELINE["confidence"]["bucket_70_80_gap"], 4),
                    "component_penalty_affected_count": component_penalty_live_impact_count - BAD_BASELINE["confidence"]["swing_component_penalty_live_impact_count"],
                },
                "pass": component_penalty_live_impact_count == 0 and not low_confidence_flood_flag,
            },
            "release_recommendation": release_recommendation,
        }

    def export_csv(self, *, lookback_days: int = 30, interval_min_minutes: int = 60) -> str:
        payload = self.get_validation_payload(
            lookback_days=lookback_days,
            interval_min_minutes=interval_min_minutes,
        )
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["section", "metric", "value"])
        writer.writerow(["summary", "validator_id", payload.get("validator_id")])
        writer.writerow(["summary", "generated_at", payload.get("generated_at")])
        writer.writerow(["summary", "baseline_id", (payload.get("baseline") or {}).get("baseline_id")])
        writer.writerow(["summary", "run_source", payload.get("run_source")])
        writer.writerow(["summary", "sample_size", payload.get("sample_size")])
        writer.writerow(["summary", "overall_status", payload.get("overall_status")])
        writer.writerow(["summary", "release_recommendation", payload.get("release_recommendation")])

        for key, value in (payload.get("hard_gates") or {}).items():
            writer.writerow(["hard_gates", key, value])
        for item in payload.get("checks") or []:
            writer.writerow(["checks", str(item.get("key") or ""), "PASS" if item.get("passed") else "FAIL"])
            writer.writerow(["checks_reason", str(item.get("key") or ""), str(item.get("reason") or "")])
        for reason in payload.get("pass_fail_reasons") or []:
            writer.writerow(["pass_fail_reasons", "reason", reason])

        self._write_section_rows(writer, "stops", payload.get("stops") or {})
        self._write_section_rows(writer, "stale_exits", payload.get("stale_exits") or {})
        self._write_section_rows(writer, "regimes", payload.get("regimes") or {})
        self._write_section_rows(writer, "confidence", payload.get("confidence") or {})
        return buffer.getvalue()

    @staticmethod
    def _avg(values: list[float]) -> float | None:
        filtered = [float(value) for value in values if value is not None]
        if not filtered:
            return None
        return sum(filtered) / len(filtered)

    @staticmethod
    def _avg_structure_gap_atr(rows: list[dict[str, Any]]) -> float | None:
        gaps = []
        for row in rows:
            atr = _as_float(row.get("atr_value"))
            structure_stop = row.get("structure_stop")
            atr_floor_stop = row.get("atr_floor_stop")
            if atr and atr > 0 and structure_stop is not None and atr_floor_stop is not None:
                gaps.append(abs(_as_float(structure_stop) - _as_float(atr_floor_stop)) / atr)
        if not gaps:
            return None
        return sum(gaps) / len(gaps)

    @staticmethod
    def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            label = str(row.get(key) or "UNKNOWN")
            counts[label] = counts.get(label, 0) + 1
        return counts

    @staticmethod
    def _win_rate_by(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            label = str(row.get(key) or "UNKNOWN")
            grouped.setdefault(label, []).append(row)
        return {
            label: round(sum(1 for row in items if _as_float(row.get("realized_r")) > 0.0) / len(items), 4)
            for label, items in grouped.items()
            if items
        }

    @staticmethod
    def _distribution_shift_ok(regime_counts: dict[str, int]) -> bool:
        trending = int(regime_counts.get("TRENDING", 0))
        high_vol = int(regime_counts.get("HIGH_VOL", 0))
        if trending == 0 and high_vol == 0:
            return False
        return trending >= high_vol

    @staticmethod
    def _overall_bucket_gap(bucket_rows: list[dict[str, Any]]) -> float | None:
        gaps = []
        for row in bucket_rows:
            expected = _as_float(row.get("avg_calibrated_confidence")) / 100.0
            actual = _as_float(row.get("win_rate"))
            gaps.append(abs(expected - actual))
        if not gaps:
            return None
        return sum(gaps) / len(gaps)

    @staticmethod
    def _run_source_label(rows: list[dict[str, Any]]) -> str:
        sources = {str(row.get("source") or "UNKNOWN").upper() for row in rows}
        if not sources:
            return "unknown"
        if sources == {"PAPER"}:
            return "paper"
        if "REPLAY" in sources or "SIMULATION" in sources:
            return "replay"
        if "INTERFACE" in sources:
            return "analyzer"
        return "mixed"

    @staticmethod
    def _write_section_rows(writer: csv.writer, section: str, data: dict[str, Any], prefix: str = "") -> None:
        for key, value in data.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                SwingPatchValidationService._write_section_rows(writer, section, value, name)
            else:
                writer.writerow([section, name, value])
