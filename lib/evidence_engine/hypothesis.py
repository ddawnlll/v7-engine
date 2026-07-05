from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.evidence_engine.claims import ClaimType


@dataclass
class HypothesisCard:
    """A structured research hypothesis that links a claim type to an
    experimental design.  Models the intervention-control-treatment pattern."""

    card_id: str
    claim_type: ClaimType
    problem: str
    proposed_mechanism: str
    intervention: str
    control: str
    data: str
    baselines: list[str]
    success_criteria: list[str]
    fail_criteria: list[str]
    max_trials: int
    trial_count: int = 0
    allowed_files: list[str] = field(default_factory=list)
    status: str = "DRAFT"  # DRAFT | REGISTERED | APPROVED | REJECTED | EXPIRED


class HypothesisRegistry:
    """Persistent registry of hypothesis cards backed by a JSON ledger file.

    The registry validates cards on registration, enforces the
    DRAFT -> REGISTERED -> APPROVED / REJECTED lifecycle, and tracks
    trial counts against ``max_trials``.
    """

    VALID_STATUSES = frozenset({"DRAFT", "REGISTERED", "APPROVED", "REJECTED", "EXPIRED"})

    def __init__(self, ledger_path: str | None = None) -> None:
        self._ledger_path: str | None = ledger_path
        self._cards: dict[str, HypothesisCard] = {}
        if ledger_path is not None and Path(ledger_path).exists():
            self._load_ledger()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, card: HypothesisCard) -> str:
        """Register (or re-register) a card.

        Returns the ``card_id`` on success.  Raises ``ValueError`` if
        the card does not pass validation.
        """
        valid, errors = self.is_valid(card)
        if not valid:
            msg = "; ".join(errors)
            raise ValueError(f"HypothesisCard validation failed: {msg}")

        card.status = "REGISTERED"
        self._cards[card.card_id] = card
        self._save_ledger()
        return card.card_id

    def get(self, card_id: str) -> HypothesisCard | None:
        return self._cards.get(card_id)

    def approve(self, card_id: str) -> bool:
        card = self._cards.get(card_id)
        if card is None or card.status != "REGISTERED":
            return False
        card.status = "APPROVED"
        self._save_ledger()
        return True

    def reject(self, card_id: str, reason: str) -> bool:
        card = self._cards.get(card_id)
        if card is None or card.status not in ("REGISTERED", "APPROVED"):
            return False
        card.status = "REJECTED"
        self._save_ledger()
        return True

    def increment_trial(self, card_id: str) -> bool:
        card = self._cards.get(card_id)
        if card is None or card.status != "REGISTERED":
            return False
        if card.trial_count >= card.max_trials:
            card.status = "EXPIRED"
            self._save_ledger()
            return False
        card.trial_count += 1
        if card.trial_count >= card.max_trials:
            card.status = "EXPIRED"
        self._save_ledger()
        return True

    def is_valid(self, card: HypothesisCard) -> tuple[bool, list[str]]:
        """Validate a card's fields before registration.

        Returns ``(True, [])`` or ``(False, [reason, ...])``.
        """
        errors: list[str] = []
        if not card.card_id:
            errors.append("card_id is required")
        if not isinstance(card.claim_type, ClaimType):
            errors.append("claim_type must be a ClaimType enum value")
        if not card.problem:
            errors.append("problem is required")
        if not card.intervention:
            errors.append("intervention is required")
        if not card.control:
            errors.append("control is required")
        if not card.data:
            errors.append("data is required")
        if not card.baselines:
            errors.append("at least one baseline is required")
        if not card.success_criteria:
            errors.append("at least one success criterion is required")
        if not card.fail_criteria:
            errors.append("at least one fail criterion is required")
        if card.max_trials < 1:
            errors.append("max_trials must be >= 1")
        if card.status not in self.VALID_STATUSES:
            errors.append(f"status must be one of {sorted(self.VALID_STATUSES)}")
        return (len(errors) == 0, errors)

    def can_implement(self, card_id: str) -> bool:
        """Check if a card is approved, not expired, and under trial limit."""
        card = self._cards.get(card_id)
        if card is None:
            return False
        if card.status not in ("REGISTERED", "APPROVED"):
            return False
        if card.trial_count >= card.max_trials:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """Serialize the registry to a plain dict (JSON-safe)."""
        return {
            "ledger_path": self._ledger_path,
            "cards": {
                cid: _card_to_dict(c) for cid, c in sorted(self._cards.items())
            },
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_ledger(self) -> None:
        if self._ledger_path is None:
            return
        path = Path(self._ledger_path)
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if "cards" not in raw:
            return
        for cid, data in raw["cards"].items():
            try:
                card = _dict_to_card(data)
                if card is not None:
                    self._cards[cid] = card
            except Exception:  # noqa: BLE001  — skip corrupt entries
                continue

    def _save_ledger(self) -> None:
        if self._ledger_path is None:
            return
        path = Path(self._ledger_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )


# ------------------------------------------------------------------
# Serialisation helpers
# ------------------------------------------------------------------

def _card_to_dict(card: HypothesisCard) -> dict[str, Any]:
    d = asdict(card)
    d["claim_type"] = card.claim_type.value
    return d


def _dict_to_card(data: dict[str, Any]) -> HypothesisCard | None:
    ids = {"card_id", "claim_type"}
    if not ids.issubset(data.keys()):
        return None
    data = dict(data)
    data["claim_type"] = ClaimType(data["claim_type"])
    return HypothesisCard(**data)
