"""Shared websocket owner lifecycle helpers for the v4 process.

Follows the same registry pattern as autonomous_runtime.py.
"""

from __future__ import annotations

import logging

from runtime.db.repos.runtime_profile_repo import RuntimeProfileRepository
from runtime.db.session import session_scope
from runtime.runtime.websocket_owner import BinanceUsdmWebsocketOwner
from runtime.services.runtime_profile_service import BINANCE_USDM_VENUE

log = logging.getLogger("v4.websocket_runtime")

_OWNERS: dict[str, BinanceUsdmWebsocketOwner] = {}


def get_websocket_owner(profile_id: str) -> BinanceUsdmWebsocketOwner | None:
    return _OWNERS.get(profile_id)


def start_websocket_owner(profile_id: str) -> BinanceUsdmWebsocketOwner | None:
    """Start a websocket owner for the given profile if eligible.

    Returns the owner if started, None if ineligible or already running.
    """
    if profile_id in _OWNERS and _OWNERS[profile_id].running:
        return _OWNERS[profile_id]

    owner = BinanceUsdmWebsocketOwner(profile_id)
    if not owner.is_eligible():
        log.info("websocket owner not eligible for profile=%s", profile_id)
        return None

    owner.start()
    _OWNERS[profile_id] = owner
    log.info("websocket owner started for profile=%s", profile_id)
    return owner


def stop_websocket_owner(profile_id: str | None = None) -> None:
    """Stop websocket owner(s).

    If profile_id is None, stop all owners.
    """
    global _OWNERS
    if profile_id is None:
        owners = list(_OWNERS.values())
        _OWNERS = {}
        for owner in owners:
            try:
                owner.stop()
            except Exception:
                log.exception("error stopping websocket owner")
        return

    owner = _OWNERS.pop(profile_id, None)
    if owner is not None:
        try:
            owner.stop()
        except Exception:
            log.exception("error stopping websocket owner for profile=%s", profile_id)


def start_eligible_websocket_owners() -> list[str]:
    """Discover all eligible Binance USDⓈ-M profiles and start websocket owners.

    Returns the list of profile IDs that were started.
    """
    repo = RuntimeProfileRepository()
    with session_scope() as session:
        profiles = repo.list_profiles(session)

    started: list[str] = []
    for profile in profiles:
        profile_id = str(profile.get("profile_id") or "").strip()
        if not profile_id:
            continue
        venue = str(profile.get("venue") or "").upper()
        if venue != BINANCE_USDM_VENUE:
            continue
        if not bool(profile.get("supports_account_reads")):
            continue
        owner = start_websocket_owner(profile_id)
        if owner is not None:
            started.append(profile_id)

    return started


__all__ = [
    "get_websocket_owner",
    "start_eligible_websocket_owners",
    "start_websocket_owner",
    "stop_websocket_owner",
]
