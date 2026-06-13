"""Runtime profile repository for tenancy identity foundation."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from runtime.db.models import RuntimeProfile

PAPER_PROFILE_ID = "paper-main"
PAPER_PROFILE_NAME = "Paper Main"
BINANCE_USDM_PROFILE_ID = "binance-usdm-main"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeProfileRepository:
    def get_profile(self, session: Session, profile_id: str = PAPER_PROFILE_ID) -> dict | None:
        row = session.query(RuntimeProfile).filter(RuntimeProfile.profile_id == profile_id).one_or_none()
        return self._to_dict(row) if row else None

    def list_profiles(self, session: Session, limit: int = 100) -> list[dict]:
        rows = session.query(RuntimeProfile).order_by(RuntimeProfile.created_at_utc.asc()).limit(limit).all()
        return [self._to_dict(row) for row in rows]

    def save_profile(self, session: Session, payload: dict) -> dict:
        row = session.query(RuntimeProfile).filter(RuntimeProfile.profile_id == payload["profile_id"]).one_or_none()
        if row is None:
            row = RuntimeProfile(**payload)
            session.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        session.commit()
        session.refresh(row)
        return self._to_dict(row)

    def ensure_paper_main(self, session: Session) -> dict:
        existing = self.get_profile(session, PAPER_PROFILE_ID)
        if existing is not None:
            return existing
        now = utc_now_iso()
        return self.save_profile(
            session,
            {
                "profile_id": PAPER_PROFILE_ID,
                "name": PAPER_PROFILE_NAME,
                "status": "ACTIVE",
                "runtime_mode": "PAPER",
                "execution_mode": "PAPER",
                "venue": "INTERNAL_PAPER",
                "product_type": "SIMULATED",
                "venue_environment": "INTERNAL",
                "api_base_url": None,
                "default_for_auto_trading": True,
                "manual_trading_enabled": True,
                "auto_trading_enabled": False,
                "read_only": False,
                "supports_account_reads": True,
                "supports_order_placement": True,
                "credential_ref": None,
                "connectivity_status": "READY",
                "last_connectivity_check_at_utc": now,
                "last_connectivity_ok_at_utc": now,
                "last_connectivity_error": None,
                "created_at_utc": now,
                "updated_at_utc": now,
            },
        )

    @staticmethod
    def _to_dict(row: RuntimeProfile | None) -> dict | None:
        if row is None:
            return None
        return {
            "id": row.id,
            "profile_id": row.profile_id,
            "name": row.name,
            "status": row.status,
            "runtime_mode": row.runtime_mode,
            "execution_mode": row.execution_mode,
            "venue": row.venue,
            "product_type": row.product_type,
            "venue_environment": row.venue_environment,
            "api_base_url": row.api_base_url,
            "default_for_auto_trading": bool(row.default_for_auto_trading),
            "manual_trading_enabled": bool(row.manual_trading_enabled),
            "auto_trading_enabled": bool(row.auto_trading_enabled),
            "read_only": bool(row.read_only),
            "supports_account_reads": bool(row.supports_account_reads),
            "supports_order_placement": bool(row.supports_order_placement),
            "credential_ref": row.credential_ref,
            "connectivity_status": row.connectivity_status,
            "last_connectivity_check_at_utc": row.last_connectivity_check_at_utc,
            "last_connectivity_ok_at_utc": row.last_connectivity_ok_at_utc,
            "last_connectivity_error": row.last_connectivity_error,
            "created_at_utc": row.created_at_utc,
            "updated_at_utc": row.updated_at_utc,
        }
