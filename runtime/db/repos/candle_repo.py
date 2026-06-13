"""Candle repository for v4."""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from runtime.db.models import Candle


class CandleRepository:
    def save_candle(self, session: Session, payload: dict) -> dict:
        row = (
            session.query(Candle)
            .filter(Candle.symbol == payload["symbol"])
            .filter(Candle.interval == payload["interval"])
            .filter(Candle.open_time_utc == payload["open_time_utc"])
            .one_or_none()
        )
        if row is None:
            row = Candle(**payload)
            session.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        session.commit()
        return self._to_dict(row)

    def replace_symbol_interval(self, session: Session, symbol: str, interval: str, payloads: list[dict]) -> dict:
        if self._matches_existing(session, symbol, interval, payloads):
            return {
                "write_skipped": True,
                "rows_written": 0,
            }
        session.execute(delete(Candle).where(Candle.symbol == symbol, Candle.interval == interval))
        if payloads:
            session.add_all([Candle(**payload) for payload in payloads])
        session.commit()
        return {
            "write_skipped": False,
            "rows_written": len(payloads),
        }

    def list_candles(self, session: Session, symbol: str, interval: str, limit: int = 200) -> list[dict]:
        rows = (
            session.query(Candle)
            .filter(Candle.symbol == symbol, Candle.interval == interval)
            .order_by(Candle.open_time_utc.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(row) for row in reversed(rows)]

    def list_candles_between(self, session: Session, symbol: str, interval: str, start_utc: str, end_utc: str) -> list[dict]:
        rows = (
            session.query(Candle)
            .filter(Candle.symbol == symbol, Candle.interval == interval)
            .filter(Candle.open_time_utc >= start_utc)
            .filter(Candle.open_time_utc <= end_utc)
            .order_by(Candle.open_time_utc.asc())
            .all()
        )
        return [self._to_dict(row) for row in rows]

    def bulk_upsert_candles(self, session: Session, payloads: list[dict]) -> int:
        written = 0
        for payload in payloads:
            row = (
                session.query(Candle)
                .filter(Candle.symbol == payload["symbol"])
                .filter(Candle.interval == payload["interval"])
                .filter(Candle.open_time_utc == payload["open_time_utc"])
                .one_or_none()
            )
            if row is None:
                session.add(Candle(**payload))
            else:
                for key, value in payload.items():
                    setattr(row, key, value)
            written += 1
        session.commit()
        return written

    def delete_symbol_interval(self, session: Session, symbol: str, interval: str) -> None:
        session.execute(delete(Candle).where(Candle.symbol == symbol, Candle.interval == interval))
        session.commit()

    def _matches_existing(self, session: Session, symbol: str, interval: str, payloads: list[dict]) -> bool:
        if not payloads:
            existing_count = int(
                session.query(Candle)
                .filter(Candle.symbol == symbol, Candle.interval == interval)
                .count()
            )
            return existing_count == 0
        existing_count = int(
            session.query(Candle)
            .filter(Candle.symbol == symbol, Candle.interval == interval)
            .count()
        )
        if existing_count != len(payloads):
            return False
        first_row = (
            session.query(Candle)
            .filter(Candle.symbol == symbol, Candle.interval == interval)
            .order_by(Candle.open_time_utc.asc())
            .first()
        )
        last_row = (
            session.query(Candle)
            .filter(Candle.symbol == symbol, Candle.interval == interval)
            .order_by(Candle.open_time_utc.desc())
            .first()
        )
        if first_row is None or last_row is None:
            return False
        first_payload = payloads[0]
        last_payload = payloads[-1]
        return (
            first_row.open_time_utc == first_payload["open_time_utc"]
            and first_row.close_time_utc == first_payload["close_time_utc"]
            and float(first_row.open) == float(first_payload["open"])
            and float(first_row.high) == float(first_payload["high"])
            and float(first_row.low) == float(first_payload["low"])
            and float(first_row.close) == float(first_payload["close"])
            and float(first_row.volume) == float(first_payload.get("volume", 0.0))
            and bool(first_row.stale) == bool(first_payload.get("stale", False))
            and last_row.open_time_utc == last_payload["open_time_utc"]
            and last_row.close_time_utc == last_payload["close_time_utc"]
            and float(last_row.open) == float(last_payload["open"])
            and float(last_row.high) == float(last_payload["high"])
            and float(last_row.low) == float(last_payload["low"])
            and float(last_row.close) == float(last_payload["close"])
            and float(last_row.volume) == float(last_payload.get("volume", 0.0))
            and bool(last_row.stale) == bool(last_payload.get("stale", False))
        )

    @staticmethod
    def _to_dict(row: Candle) -> dict:
        return {
            "id": row.id,
            "symbol": row.symbol,
            "interval": row.interval,
            "open_time_utc": row.open_time_utc,
            "close_time_utc": row.close_time_utc,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "volume": row.volume,
            "source": row.source,
            "stale": row.stale,
        }
