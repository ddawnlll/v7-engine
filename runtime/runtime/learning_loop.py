"""Background refresh loop for adaptive learning profile."""

from __future__ import annotations

import logging
import time
from threading import Event, Thread

from runtime.db.repos.settings_repo import SettingsRepository
from runtime.db.repos.state_repo import StateRepository
from runtime.db.session import session_scope
from runtime.services.learning_service import LearningService

log = logging.getLogger("v4.learning_loop")

_LOOP = None


class LearningLoop:
    def __init__(
        self,
        learning_service: LearningService | None = None,
        settings_repo: SettingsRepository | None = None,
        state_repo: StateRepository | None = None,
    ) -> None:
        self.learning_service = learning_service or LearningService()
        self.settings_repo = settings_repo or SettingsRepository()
        self.state_repo = state_repo or StateRepository()
        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self.run_forever, name="v4-learning-loop", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def run_once(self) -> dict | None:
        with session_scope() as session:
            settings = self.settings_repo.get_all(session)
        lookback_days = int(float(settings.get("LEARNING_LOOKBACK_DAYS", "30")))
        min_confidence = float(settings.get("LEARNING_MIN_CONFIDENCE", "0.6"))
        try:
            profile = self.learning_service.get_learning_adjustments(
                lookback_days=lookback_days,
                min_confidence=min_confidence,
                force_refresh=True,
            )
            with session_scope() as session:
                self.state_repo.set(
                    session,
                    "learning_status",
                    {
                        "timestamp": profile.get("generated_at"),
                        "status": profile.get("status"),
                        "samples": profile.get("samples"),
                    },
                )
            return profile
        except Exception as exc:
            log.exception("learning profile refresh failed")
            with session_scope() as session:
                self.state_repo.set(
                    session,
                    "learning_status",
                    {
                        "timestamp": None,
                        "status": "failed",
                        "error": str(exc),
                    },
                )
            return None

    def run_forever(self) -> None:
        while not self._stop_event.is_set():
            with session_scope() as session:
                settings = self.settings_repo.get_all(session)
            refresh_seconds = max(60, int(float(settings.get("LEARNING_REFRESH_SECONDS", "300"))))
            self.run_once()
            self._stop_event.wait(refresh_seconds)


def get_learning_loop() -> LearningLoop:
    global _LOOP
    if _LOOP is None:
        _LOOP = LearningLoop()
    return _LOOP


def start_learning_loop() -> LearningLoop:
    loop = get_learning_loop()
    loop.start()
    return loop


def stop_learning_loop() -> None:
    global _LOOP
    if _LOOP is None:
        return
    _LOOP.stop()
