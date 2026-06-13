"""Execution account repository built on profile-owned account storage."""

from __future__ import annotations

from sqlalchemy.orm import Session

from runtime.db.models import ProfileAccount
from runtime.db.repos._helpers import loads_json


class ExecutionAccountRepository:
    def get_account_by_id(self, session: Session, account_id: str) -> dict | None:
        row = session.query(ProfileAccount).filter(ProfileAccount.account_id == str(account_id or "")).one_or_none()
        return self._to_dict(row) if row else None

    def get_default_account(self, session: Session, profile_id: str) -> dict | None:
        rows = (
            session.query(ProfileAccount)
            .filter(ProfileAccount.profile_id == str(profile_id or ""))
            .order_by(ProfileAccount.account_key.asc(), ProfileAccount.id.asc())
            .limit(1)
            .all()
        )
        if not rows:
            return None
        return self._to_dict(rows[0])

    @staticmethod
    def _to_dict(row: ProfileAccount) -> dict:
        return {
            "id": row.id,
            "account_id": row.account_id,
            "account_key": row.account_key,
            "profile_id": row.profile_id,
            "account_type": row.account_type,
            "venue_account_key": row.venue_account_key,
            "balance_ccy": row.balance_ccy,
            "balance": float(row.balance),
            "available_balance": float(row.available_balance),
            "equity": float(row.equity),
            "margin_used": float(row.margin_used),
            "payload": loads_json(getattr(row, "payload_json", "{}"), {}),
            "as_of_utc": row.as_of_utc,
            "created_at_utc": row.created_at_utc,
            "updated_at_utc": row.updated_at_utc,
        }
