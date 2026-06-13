"""Symbol-level tactical throttling for repeat offenders."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from runtime.db.models import Order, Signal
from runtime.db.repos._helpers import loads_json
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.repos.settings_repo import SettingsRepository, split_csv
from runtime.db.session import session_scope


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class UniverseFilterService:
    def __init__(self, settings_repo: SettingsRepository | None = None) -> None:
        self.settings_repo = settings_repo or SettingsRepository()

    def evaluate(self, symbols: list[str] | None = None, *, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        with session_scope() as session:
            settings = self.settings_repo.get_all(session, profile_id=profile_id)
            return self._evaluate_session(session, settings=settings, symbols=symbols, profile_id=profile_id)

    def _evaluate_session(self, session: Session, *, settings: dict[str, str], symbols: list[str] | None = None, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        enabled = str(settings.get("SYMBOL_THROTTLE_ENABLED", "true")).lower() in {"1", "true", "yes", "on"}
        lookback_trades = max(3, int(_as_float(settings.get("SYMBOL_THROTTLE_LOOKBACK_TRADES"), 12)))
        max_consecutive = max(2, int(_as_float(settings.get("SYMBOL_THROTTLE_MAX_CONSECUTIVE_STOP_HITS"), 3)))
        max_stop_rate_pct = max(1.0, _as_float(settings.get("SYMBOL_THROTTLE_MAX_STOP_HIT_RATE_PCT"), 70.0))
        cooldown_minutes = max(1, int(_as_float(settings.get("SYMBOL_THROTTLE_COOLDOWN_MINUTES"), 240)))
        seeded_symbols = {item.upper() for item in split_csv(settings.get("SYMBOL_THROTTLE_SEEDED_SYMBOLS"))}
        requested_symbols = {str(item).upper() for item in (symbols or []) if str(item).strip()}
        target_symbols = requested_symbols or seeded_symbols

        query = (
            session.query(Order, Signal)
            .outerjoin(Signal, Signal.signal_id == Order.signal_id)
            .filter(Order.profile_id == profile_id)
            .filter(Order.status != "OPEN")
            .order_by(Order.closed_at_utc.desc(), Order.opened_at_utc.desc())
        )
        rows = query.all()
        by_symbol: dict[str, list[tuple[Order, Signal | None]]] = {}
        for order, signal in rows:
            symbol = str(order.symbol or "").upper()
            if target_symbols and symbol not in target_symbols:
                continue
            by_symbol.setdefault(symbol, []).append((order, signal))

        states = []
        now = datetime.now(timezone.utc)
        all_symbols = sorted(target_symbols | set(by_symbol.keys()))
        for symbol in all_symbols:
            symbol_rows = by_symbol.get(symbol, [])[:lookback_trades]
            stop_hits = 0
            consecutive_stop_hits = 0
            latest_stop_time: datetime | None = None
            for index, (order, _signal) in enumerate(symbol_rows):
                payload = loads_json(order.payload_json, {})
                close_reason = str(payload.get("close_reason") or "").upper()
                if close_reason == "HIT_SL":
                    stop_hits += 1
                    if index == 0 or consecutive_stop_hits == index:
                        consecutive_stop_hits += 1
                    if latest_stop_time is None:
                        latest_stop_time = _parse_iso(order.closed_at_utc) or _parse_iso(order.opened_at_utc)
            trade_count = len(symbol_rows)
            stop_rate_pct = (stop_hits / trade_count) * 100.0 if trade_count else 0.0
            throttle_until = None
            active_rules: list[str] = []
            reason = None
            if symbol in seeded_symbols:
                active_rules.append("seeded_guardrail")
                reason = "Seeded temporary throttle from engine diagnostic."
            if consecutive_stop_hits >= max_consecutive:
                active_rules.append("consecutive_stop_hits")
                reason = f"{consecutive_stop_hits} consecutive stop hits reached the throttle rule."
            if trade_count and stop_rate_pct >= max_stop_rate_pct:
                active_rules.append("rolling_stop_rate")
                reason = f"Recent stop-hit rate {stop_rate_pct:.1f}% exceeded {max_stop_rate_pct:.1f}%."
            if latest_stop_time is not None and active_rules:
                throttle_until = latest_stop_time + timedelta(minutes=cooldown_minutes)
            throttled = enabled and bool(active_rules) and (throttle_until is None or throttle_until > now)
            cooldown_remaining_minutes = max(0, int((throttle_until - now).total_seconds() // 60)) if throttled and throttle_until else None

            micro = self._microstructure_summary(symbol_rows)
            states.append({
                "symbol": symbol,
                "throttled": throttled,
                "enabled": enabled,
                "reason": reason,
                "active_rules": active_rules,
                "trade_count": trade_count,
                "stop_hits": stop_hits,
                "stop_hit_rate_pct": round(stop_rate_pct, 2),
                "consecutive_stop_hits": consecutive_stop_hits,
                "cooldown_until_utc": throttle_until.isoformat() if throttle_until else None,
                "cooldown_remaining_minutes": cooldown_remaining_minutes,
                "seeded": symbol in seeded_symbols,
                "microstructure": micro,
            })

        throttled_symbols = [item for item in states if item["throttled"]]
        return {
            "enabled": enabled,
            "rules": {
                "lookback_trades": lookback_trades,
                "max_consecutive_stop_hits": max_consecutive,
                "max_stop_hit_rate_pct": max_stop_rate_pct,
                "cooldown_minutes": cooldown_minutes,
            },
            "seeded_symbols": sorted(seeded_symbols),
            "total_symbols": len(states),
            "total_throttled": len(throttled_symbols),
            "throttled_symbols": throttled_symbols,
            "items": states,
            "generated_at": now.isoformat(),
        }

    @staticmethod
    def _microstructure_summary(rows: list[tuple[Order, Signal | None]]) -> dict[str, Any]:
        spreads: list[float] = []
        micro_devs: list[float] = []
        intensities: list[float] = []
        vol_ratios: list[float] = []
        sweep_hits = 0
        wickiness_scores: list[float] = []
        count = 0
        for _order, signal in rows:
            if signal is None:
                continue
            snapshot = loads_json(getattr(signal, "snapshot_json", "{}"), {})
            spreads.append(_as_float(snapshot.get("orderbook_spread_bps")))
            micro_devs.append(_as_float(snapshot.get("orderbook_microprice_deviation_bps")))
            intensities.append(_as_float(snapshot.get("trade_intensity"), 1.0))
            vol_ratios.append(_as_float(snapshot.get("vol_ratio"), 0.0))
            if bool(snapshot.get("bullish_sweep")) or bool(snapshot.get("bearish_sweep")):
                sweep_hits += 1
            recent_high = _as_float(snapshot.get("recent_high"), 0.0)
            recent_low = _as_float(snapshot.get("recent_low"), 0.0)
            price = _as_float(snapshot.get("price"), 0.0)
            range_size = max(recent_high - recent_low, 0.0)
            if range_size > 0 and price > 0:
                wickiness_scores.append(min(1.0, range_size / max(price, 1e-9)))
            count += 1
        def _avg(values: list[float]) -> float | None:
            if not values:
                return None
            return round(sum(values) / len(values), 4)
        return {
            "samples": count,
            "avg_spread_bps": _avg([value for value in spreads if value > 0]),
            "avg_microprice_deviation_bps": _avg([abs(value) for value in micro_devs if value != 0]),
            "avg_trade_intensity": _avg([value for value in intensities if value > 0]),
            "avg_vol_ratio": _avg([value for value in vol_ratios if value > 0]),
            "sweep_frequency": round(sweep_hits / count, 4) if count else 0.0,
            "wickiness_score": _avg([value for value in wickiness_scores if value > 0]),
        }
