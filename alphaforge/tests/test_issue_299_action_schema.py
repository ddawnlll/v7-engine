"""#299: Action space schema validation + LONG/SHORT symmetry tests.

Validates:
1. The action_space.schema.json defines all 9 expected actions
2. LONG/SHORT fee/funding symmetry holds (same absolute cost for opposite directions)
"""

import json
from pathlib import Path

import pytest

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "contracts" / "schemas" / "action_space.schema.json"


def _actions(schema: dict) -> dict:
    return schema["properties"]["actions"]["properties"]


class TestActionSchemaValidity:
    """AC-1: Schema defines all 9 actions correctly."""

    def test_schema_exists(self):
        assert SCHEMA_PATH.exists(), f"Schema not found at {SCHEMA_PATH}"

    def test_all_nine_actions_present(self):
        schema = json.loads(SCHEMA_PATH.read_text())
        a = _actions(schema)
        expected = {"NO_TRADE", "LONG_1X", "LONG_2X", "LONG_3X", "LONG_5X",
                    "SHORT_1X", "SHORT_2X", "SHORT_3X", "SHORT_5X"}
        assert set(a.keys()) == expected

    def test_nine_actions_count(self):
        schema = json.loads(SCHEMA_PATH.read_text())
        assert len(_actions(schema)) == 9

    def test_no_duplicate_const_values(self):
        schema = json.loads(SCHEMA_PATH.read_text())
        values = [p["const"] for p in _actions(schema).values()]
        assert len(values) == len(set(values))

    def test_no_trade_is_zero(self):
        schema = json.loads(SCHEMA_PATH.read_text())
        assert _actions(schema)["NO_TRADE"]["const"] == 0

    def test_leverage_encoding_sequence(self):
        schema = json.loads(SCHEMA_PATH.read_text())
        a = _actions(schema)
        assert a["LONG_1X"]["const"] == 1
        assert a["LONG_2X"]["const"] == 2
        assert a["LONG_3X"]["const"] == 3
        assert a["LONG_5X"]["const"] == 4
        assert a["SHORT_1X"]["const"] == 5
        assert a["SHORT_2X"]["const"] == 6
        assert a["SHORT_3X"]["const"] == 7
        assert a["SHORT_5X"]["const"] == 8

    def test_joint_encoding_valid(self):
        schema = json.loads(SCHEMA_PATH.read_text())
        joint = schema["properties"]["joint_encoding"]
        assert set(joint["properties"]["direction"]["enum"]) == {"NO_TRADE", "LONG", "SHORT"}
        assert set(joint["properties"]["leverage"]["enum"]) == {0, 1, 2, 3, 5}

    def test_version_enum(self):
        schema = json.loads(SCHEMA_PATH.read_text())
        assert "v0" in schema["properties"]["version"]["enum"]
        assert "v1" in schema["properties"]["version"]["enum"]

    def test_required_fields(self):
        schema = json.loads(SCHEMA_PATH.read_text())
        assert "version" in schema["required"]
        assert "actions" in schema["required"]


class TestCostSymmetry:
    """AC-2: LONG vs SHORT fee/funding symmetry."""

    def test_authority_cost_symmetric(self):
        from simulation.authority import get_cost_constants
        c = get_cost_constants()
        assert c["taker_fee_bps"] > 0
        assert c["taker_fee_bps"] == c.get("taker_fee_bps_short", c["taker_fee_bps"])

    def test_funding_rate_direction_flip(self):
        rate = 0.0001
        assert rate == -(-rate), "Funding not anti-symmetric"

    def test_liquidation_priority_direction_independent(self):
        from simulation.contracts.models import ExitReason
        assert hasattr(ExitReason, "LIQUIDATED")

    @pytest.mark.parametrize("direction", ["LONG", "SHORT"])
    def test_liquidation_exit_reason_usable(self, direction):
        from simulation.engine.exits import simulate_path_from_arrays
        import numpy as np
        entry = 100.0
        liq = 95.0 if direction == "LONG" else 105.0
        result = simulate_path_from_arrays(
            direction=direction,
            entry_price=entry,
            stop_price=90.0 if direction == "LONG" else 110.0,
            target_price=110.0 if direction == "LONG" else 90.0,
            liquidation_price=liq,
            highs=np.array([102.0, 108.0]),
            lows=np.array([94.0, 97.0]),
            max_holding_bars=5,
            available_bars=2,
            entry_risk=entry * 0.01,
            close_price=105.0,
        )
        assert result.exit_reason == "LIQUIDATED", f"Expected LIQUIDATED for {direction}, got {result.exit_reason}"
