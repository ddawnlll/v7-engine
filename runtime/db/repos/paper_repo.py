"""Paper/profile account repository for v4."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from runtime.db.models import PaperAccount, ProfileAccount
from runtime.db.repos._helpers import loads_json
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID

DEFAULT_ACCOUNT_KEY = "default"
DEFAULT_ACCOUNT_TYPE = "PAPER_CASH"
DEFAULT_BALANCE_CCY = "USD"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PaperAccountRepository:
    def get_account(
        self,
        session: Session,
        account_key: str = DEFAULT_ACCOUNT_KEY,
        *,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict | None:
        row = (
            session.query(ProfileAccount)
            .filter(ProfileAccount.profile_id == str(profile_id or PAPER_PROFILE_ID))
            .filter(ProfileAccount.account_key == account_key)
            .one_or_none()
        )
        if row is None:
            return None
        return self._to_dict(row)

    def get_or_create_account(
        self,
        session: Session,
        *,
        account_key: str = DEFAULT_ACCOUNT_KEY,
        initial_balance: float = 100.0,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict:
        resolved_profile_id = str(profile_id or PAPER_PROFILE_ID)
        row = (
            session.query(ProfileAccount)
            .filter(ProfileAccount.profile_id == resolved_profile_id)
            .filter(ProfileAccount.account_key == account_key)
            .one_or_none()
        )
        if row is None:
            legacy = session.query(PaperAccount).filter(PaperAccount.account_key == account_key).one_or_none()
            balance = float(legacy.balance) if legacy is not None else float(initial_balance)
            now = utc_now_iso()
            row = ProfileAccount(
                account_id=self._account_id(resolved_profile_id, account_key),
                profile_id=resolved_profile_id,
                account_key=account_key,
                account_type=DEFAULT_ACCOUNT_TYPE,
                venue_account_key=None,
                balance_ccy=DEFAULT_BALANCE_CCY,
                balance=balance,
                available_balance=balance,
                equity=balance,
                margin_used=0.0,
                payload_json="{}",
                as_of_utc=now,
                created_at_utc=now,
                updated_at_utc=now,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
        return self._to_dict(row)

    def get_balance(
        self,
        session: Session,
        *,
        account_key: str = DEFAULT_ACCOUNT_KEY,
        initial_balance: float = 100.0,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> float:
        account = self.get_or_create_account(
            session,
            account_key=account_key,
            initial_balance=initial_balance,
            profile_id=profile_id,
        )
        return float(account["balance"])

    def update_balance(
        self,
        session: Session,
        delta: float,
        *,
        account_key: str = DEFAULT_ACCOUNT_KEY,
        initial_balance: float = 100.0,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict:
        resolved_profile_id = str(profile_id or PAPER_PROFILE_ID)
        row = (
            session.query(ProfileAccount)
            .filter(ProfileAccount.profile_id == resolved_profile_id)
            .filter(ProfileAccount.account_key == account_key)
            .one_or_none()
        )
        now = utc_now_iso()
        if row is None:
            row = ProfileAccount(
                account_id=self._account_id(resolved_profile_id, account_key),
                profile_id=resolved_profile_id,
                account_key=account_key,
                account_type=DEFAULT_ACCOUNT_TYPE,
                venue_account_key=None,
                balance_ccy=DEFAULT_BALANCE_CCY,
                balance=float(initial_balance),
                available_balance=float(initial_balance),
                equity=float(initial_balance),
                margin_used=0.0,
                payload_json="{}",
                as_of_utc=now,
                created_at_utc=now,
                updated_at_utc=now,
            )
            session.add(row)
            session.flush()
        new_balance = float(row.balance) + float(delta)
        row.balance = new_balance
        row.available_balance = new_balance
        row.equity = new_balance
        row.margin_used = 0.0
        row.as_of_utc = now
        row.updated_at_utc = now
        session.commit()
        session.refresh(row)
        return self._to_dict(row)

    def set_balance(
        self,
        session: Session,
        balance: float,
        *,
        account_key: str = DEFAULT_ACCOUNT_KEY,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict:
        resolved_profile_id = str(profile_id or PAPER_PROFILE_ID)
        row = (
            session.query(ProfileAccount)
            .filter(ProfileAccount.profile_id == resolved_profile_id)
            .filter(ProfileAccount.account_key == account_key)
            .one_or_none()
        )
        now = utc_now_iso()
        if row is None:
            row = ProfileAccount(
                account_id=self._account_id(resolved_profile_id, account_key),
                profile_id=resolved_profile_id,
                account_key=account_key,
                account_type=DEFAULT_ACCOUNT_TYPE,
                venue_account_key=None,
                balance_ccy=DEFAULT_BALANCE_CCY,
                balance=float(balance),
                available_balance=float(balance),
                equity=float(balance),
                margin_used=0.0,
                payload_json="{}",
                as_of_utc=now,
                created_at_utc=now,
                updated_at_utc=now,
            )
            session.add(row)
        else:
            row.balance = float(balance)
            row.available_balance = float(balance)
            row.equity = float(balance)
            row.margin_used = 0.0
            row.as_of_utc = now
            row.updated_at_utc = now
        session.commit()
        session.refresh(row)
        return self._to_dict(row)

    def reset_balance(
        self,
        session: Session,
        *,
        account_key: str = DEFAULT_ACCOUNT_KEY,
        initial_balance: float = 100.0,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict:
        return self.set_balance(session, float(initial_balance), account_key=account_key, profile_id=profile_id)

    @staticmethod
    def _account_id(profile_id: str, account_key: str) -> str:
        return f"{profile_id}:{account_key}"

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
            "created_at": row.created_at_utc,
            "updated_at": row.updated_at_utc,
        }
