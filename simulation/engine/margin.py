"""
Isolated-margin position model for Binance USDⓈ-M perpetual swaps.

P0 scope: ISOLATED margin only. Computes initial margin, maintenance
margin, liquidation price, and liquidation distance for a given
leverage tier and Binance bracket snapshot.

Uses no live network calls. All inputs are explicit deterministic
snapshots consumed by the Simulation engine.

Reference: Binance USDⓈ-M Futures API
  - GET /fapi/v1/leverageBracket
  - POST /fapi/v1/marginType (ISOLATED)
"""

from __future__ import annotations

from simulation.contracts.models import (
    BinanceBracketSnapshot,
    LeverageTier,
    PositionMargin,
)

def resolve_bracket_snapshot(
    *, symbol: str, notional: float, leverage: int,
    snapshots: tuple[BinanceBracketSnapshot, ...] | list[BinanceBracketSnapshot],
) -> BinanceBracketSnapshot:
    """Resolve the smallest valid exchange bracket for symbol/notional.

    This is intentionally fail-closed.  A leverage-native simulation cannot
    claim Binance parity from a universal maintenance-margin ratio.
    """
    if notional <= 0:
        raise ValueError("notional must be > 0")
    candidates = [
        snap for snap in snapshots
        if snap.symbol == symbol and snap.leverage >= leverage and snap.notional_cap_usd >= notional
    ]
    if not candidates:
        raise ValueError(
            f"no bracket snapshot covers {symbol} notional={notional} leverage={leverage}"
        )
    return min(candidates, key=lambda snap: (snap.notional_cap_usd, snap.tier))


def compute_isolated_margin(
    *,
    leverage: int,
    entry_price: float,
    notional: float,
    direction: str,  # "LONG" or "SHORT"
    bracket: BinanceBracketSnapshot | None = None,
) -> PositionMargin:
    """Compute isolated-margin position parameters.

    Args:
        leverage: Leverage multiplier (1–10). 0 means NO_TRADE.
        entry_price: Entry price of the asset.
        notional: Position notional in quote currency.
        direction: "LONG" or "SHORT".
        bracket: Explicit resolved Binance bracket. Required for leverage >1.

    Returns:
        PositionMargin with initial margin, maintenance margin,
        liquidation price, and liquidation distance.

    Raises:
        ValueError: if leverage < 1, or margin_type is not ISOLATED.

    Formula (Binance USDⓈ-M isolated margin):

        IMR = 1 / leverage
        initial_margin = notional × IMR
        maintenance_margin = notional × MMR
        liquidation_distance_pct = IMR - MMR

        LONG:  liq_price = entry × (1 - liquidation_distance_pct)
        SHORT: liq_price = entry × (1 + liquidation_distance_pct)

    1x leverage → IMR = 1.0, liq_distance < 0 → no liquidation possible.
    """
    if leverage < 1:
        raise ValueError(f"leverage must be >= 1, got {leverage}")
    if direction.upper() not in ("LONG", "SHORT"):
        raise ValueError(f"direction must be LONG or SHORT, got {direction}")

    if entry_price <= 0:
        raise ValueError("entry_price must be > 0")
    if notional <= 0:
        raise ValueError("notional must be > 0")
    if leverage > 1 and bracket is None:
        raise ValueError("explicit bracket snapshot is required for leverage > 1")
    if bracket is not None and bracket.notional_cap_usd < notional:
        raise ValueError("bracket snapshot does not cover requested notional")
    if bracket is not None and bracket.leverage < leverage:
        raise ValueError("bracket snapshot does not cover requested leverage")

    _mmr = bracket.maintenance_margin_ratio if bracket is not None else 0.0
    imr = 1.0 / leverage

    initial_margin = notional * imr
    maintenance_margin_val = notional * _mmr
    liq_distance_pct = imr - _mmr

    # Liquidation price
    if leverage == 1 or liq_distance_pct <= 0:
        # 1x → no liquidation possible (spot-equivalent, no borrow)
        liq_price = None
        liq_distance_pct = 0.0
    elif direction.upper() == "LONG":
        liq_price = entry_price * (1.0 - liq_distance_pct)
    else:  # SHORT
        liq_price = entry_price * (1.0 + liq_distance_pct)

    return PositionMargin(
        leverage=leverage,
        margin_type="ISOLATED",
        initial_margin_ratio=imr,
        maintenance_margin_ratio=_mmr,
        quantity=notional / entry_price if entry_price > 0 else 0.0,
        notional=notional,
        entry_price=entry_price,
        liquidation_price=liq_price,
        liquidation_distance_pct=liq_distance_pct,
        bracket_snapshot_version=(bracket.bracket_snapshot_version if bracket else "not-required-1x"),
        bracket_tier=(bracket.tier if bracket else 0),
    )


def leverage_to_tier(leverage: int) -> LeverageTier:
    """Map leverage integer to LeverageTier enum."""
    mapping: dict[int, LeverageTier] = {
        0: LeverageTier.NO_TRADE,
        1: LeverageTier.LEV_1X,
        2: LeverageTier.LEV_2X,
        3: LeverageTier.LEV_3X,
        5: LeverageTier.LEV_5X,
        7: LeverageTier.LEV_7X,
        10: LeverageTier.LEV_10X,
    }
    return mapping.get(leverage, LeverageTier.LEV_1X)


# ── Action space mapping (v2, 13 actions) ─────────────────────────────
#
# v2 preserves v1 IDs (0-8) and adds new actions 9-12.
# v1: 0=NO_TRADE, 1-4=LONG_1X..5X, 5-8=SHORT_1X..5X
# v2 adds: 9=LONG_7X, 10=LONG_10X, 11=SHORT_7X, 12=SHORT_10X

# Integer label → (direction, leverage)
ACTION_ID_TO_DIRECTION_LEVERAGE: dict[int, tuple[str, int]] = {
    0:  ("NO_TRADE", 0),
    1:  ("LONG", 1),
    2:  ("LONG", 2),
    3:  ("LONG", 3),
    4:  ("LONG", 5),
    5:  ("SHORT", 1),
    6:  ("SHORT", 2),
    7:  ("SHORT", 3),
    8:  ("SHORT", 5),
    9:  ("LONG", 7),
    10: ("LONG", 10),
    11: ("SHORT", 7),
    12: ("SHORT", 10),
}

# Action label → integer
ACTION_LABEL_TO_ID: dict[str, int] = {
    "NO_TRADE": 0,
    "LONG_1X": 1, "LONG_2X": 2, "LONG_3X": 3, "LONG_5X": 4,
    "SHORT_1X": 5, "SHORT_2X": 6, "SHORT_3X": 7, "SHORT_5X": 8,
    "LONG_7X": 9, "LONG_10X": 10, "SHORT_7X": 11, "SHORT_10X": 12,
}

# Integer → human-readable label
ACTION_ID_TO_LABEL: dict[int, str] = {v: k for k, v in ACTION_LABEL_TO_ID.items()}

# All valid v2 action IDs
VALID_V2_ACTION_IDS: set[int] = set(ACTION_ID_TO_DIRECTION_LEVERAGE.keys())
VALID_V2_ACTION_COUNT: int = len(VALID_V2_ACTION_IDS)  # 13


def action_id_is_valid_v2(action_id: int) -> bool:
    """Check if an integer action ID is valid in the v2 action space."""
    return action_id in VALID_V2_ACTION_IDS


def direction_leverage_for_action(action_id: int) -> tuple[str, int]:
    """Return (direction, leverage) for a v2 action ID.

    Raises ValueError for invalid IDs.
    """
    if action_id not in ACTION_ID_TO_DIRECTION_LEVERAGE:
        raise ValueError(
            f"Invalid v2 action ID {action_id}. Valid range: 0-12."
        )
    return ACTION_ID_TO_DIRECTION_LEVERAGE[action_id]
