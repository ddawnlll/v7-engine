"""Shared autonomous loop lifecycle helpers for the v4 process."""

from __future__ import annotations

from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.runtime.autonomous_loop import AutonomousLoop

_LOOPS: dict[str, AutonomousLoop] = {}


def get_autonomous_loop(profile_id: str = PAPER_PROFILE_ID) -> AutonomousLoop:
    resolved_profile_id = str(profile_id or PAPER_PROFILE_ID)
    loop = _LOOPS.get(resolved_profile_id)
    if loop is None:
        loop = AutonomousLoop(profile_id=resolved_profile_id)
        _LOOPS[resolved_profile_id] = loop
    return loop


def start_autonomous_loop(profile_id: str = PAPER_PROFILE_ID) -> AutonomousLoop:
    loop = get_autonomous_loop(profile_id)
    loop.start()
    return loop


def stop_autonomous_loop(profile_id: str | None = None) -> None:
    global _LOOPS
    if profile_id is None:
        loops = list(_LOOPS.values())
        _LOOPS = {}
        for loop in loops:
            loop.stop()
        return

    resolved_profile_id = str(profile_id or PAPER_PROFILE_ID)
    loop = _LOOPS.pop(resolved_profile_id, None)
    if loop is not None:
        loop.stop()
