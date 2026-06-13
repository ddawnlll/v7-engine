"""Shadow policy decision persistence."""

from __future__ import annotations

from sqlalchemy.orm import Session

from runtime.db.models import ExpectancyLabelProfile, ShadowPolicyDecision
from runtime.db.repos._helpers import loads_json
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID


class ShadowPolicyRepository:
    def save_shadow_decision(self, session: Session, payload: dict) -> dict:
        payload = {**payload, "profile_id": str(payload.get("profile_id") or PAPER_PROFILE_ID)}
        row = (
            session.query(ShadowPolicyDecision)
            .filter(ShadowPolicyDecision.signal_id == payload["signal_id"])
            .filter(ShadowPolicyDecision.profile_id == payload["profile_id"])
            .one_or_none()
        )
        if row is None:
            row = ShadowPolicyDecision(**payload)
            session.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        session.commit()
        return self._shadow_to_dict(row)

    def get_shadow_decision(self, session: Session, signal_id: str, profile_id: str = PAPER_PROFILE_ID) -> dict | None:
        row = (
            session.query(ShadowPolicyDecision)
            .filter(ShadowPolicyDecision.signal_id == signal_id)
            .filter(ShadowPolicyDecision.profile_id == profile_id)
            .one_or_none()
        )
        return self._shadow_to_dict(row) if row else None

    def list_recent_shadow_decisions(self, session: Session, limit: int = 50, profile_id: str = PAPER_PROFILE_ID) -> list[dict]:
        rows = (
            session.query(ShadowPolicyDecision)
            .filter(ShadowPolicyDecision.profile_id == profile_id)
            .order_by(ShadowPolicyDecision.generated_at_utc.desc())
            .limit(limit)
            .all()
        )
        return [self._shadow_to_dict(row) for row in rows]

    def save_expectancy_profiles(self, session: Session, payloads: list[dict]) -> list[dict]:
        saved: list[dict] = []
        for payload in payloads:
            row = (
                session.query(ExpectancyLabelProfile)
                .filter(ExpectancyLabelProfile.learning_regime == payload["learning_regime"])
                .filter(ExpectancyLabelProfile.lookback_days == payload["lookback_days"])
                .one_or_none()
            )
            if row is None:
                row = ExpectancyLabelProfile(**payload)
                session.add(row)
            else:
                for key, value in payload.items():
                    setattr(row, key, value)
            saved.append(payload)
        session.commit()
        return [self.get_expectancy_profile(session, item["learning_regime"], item["lookback_days"]) for item in saved]

    def get_expectancy_profile(self, session: Session, learning_regime: str, lookback_days: int = 30) -> dict | None:
        row = (
            session.query(ExpectancyLabelProfile)
            .filter(ExpectancyLabelProfile.learning_regime == learning_regime)
            .filter(ExpectancyLabelProfile.lookback_days == int(lookback_days))
            .one_or_none()
        )
        return self._expectancy_to_dict(row) if row else None

    def list_expectancy_profiles(self, session: Session, lookback_days: int = 30, limit: int = 200) -> list[dict]:
        rows = (
            session.query(ExpectancyLabelProfile)
            .filter(ExpectancyLabelProfile.lookback_days == int(lookback_days))
            .order_by(ExpectancyLabelProfile.samples.desc(), ExpectancyLabelProfile.created_at_utc.desc())
            .limit(limit)
            .all()
        )
        return [self._expectancy_to_dict(row) for row in rows]

    @staticmethod
    def _shadow_to_dict(row: ShadowPolicyDecision) -> dict:
        return {
            "id": row.id,
            "signal_id": row.signal_id,
            "profile_id": getattr(row, "profile_id", PAPER_PROFILE_ID),
            "generated_at_utc": row.generated_at_utc,
            "recommended_action": row.recommended_action,
            "support_samples": row.support_samples,
            "expected_reward": row.expected_reward,
            "uncertainty_score": row.uncertainty_score,
            "learning_regime": row.learning_regime,
            "similar_case_count": row.similar_case_count,
            "reason_summary": row.reason_summary,
            "payload": loads_json(row.payload_json, {}),
        }

    @staticmethod
    def _expectancy_to_dict(row: ExpectancyLabelProfile) -> dict:
        return {
            "id": row.id,
            "learning_regime": row.learning_regime,
            "lookback_days": row.lookback_days,
            "samples": row.samples,
            "expected_r": row.expected_r,
            "stop_hit_probability": row.stop_hit_probability,
            "target_hit_probability": row.target_hit_probability,
            "avg_mae": row.avg_mae,
            "avg_mfe": row.avg_mfe,
            "avg_hold_minutes": row.avg_hold_minutes,
            "created_at_utc": row.created_at_utc,
        }
