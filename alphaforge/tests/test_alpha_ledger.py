"""Tests for AlphaLedger — persistent alpha candidate registry."""

import json
import tempfile
from pathlib import Path

import pytest

from alphaforge.reports.alpha_ledger import (
    AlphaLedger,
    STATUS_ACTIVE,
    STATUS_REJECTED,
    STATUS_CONTAMINATED,
    STATUS_HOLD,
    DATA_REAL,
    DATA_SYNTHETIC,
)


@pytest.fixture
def tmp_ledger(tmp_path: Path) -> AlphaLedger:
    """Return an AlphaLedger backed by a temporary file."""
    return AlphaLedger(ledger_path=tmp_path / "test_ledger.json")


class TestAlphaLedgerBasic:
    def test_empty_ledger(self, tmp_ledger: AlphaLedger) -> None:
        assert tmp_ledger.alphas == []
        assert tmp_ledger.summary["total_alphas"] == 0

    def test_add_alpha(self, tmp_ledger: AlphaLedger) -> None:
        entry = tmp_ledger.add_alpha(
            alpha_id="test_alpha_1",
            run_id="run-001",
            mode="SCALP",
            name="Test Alpha",
            thesis="Test thesis",
            source="factor_sprint",
            status=STATUS_ACTIVE,
            data_source=DATA_REAL,
            symbols=["BTCUSDT"],
        )
        assert entry["alpha_id"] == "test_alpha_1"
        assert entry["mode"] == "SCALP"
        assert len(tmp_ledger.alphas) == 1

    def test_add_duplicate_raises(self, tmp_ledger: AlphaLedger) -> None:
        tmp_ledger.add_alpha(
            alpha_id="dup", run_id="r1", mode="SCALP", name="Dup",
            thesis="t", source="xgb", status=STATUS_ACTIVE,
            data_source=DATA_REAL, symbols=["BTCUSDT"],
        )
        with pytest.raises(ValueError, match="already exists"):
            tmp_ledger.add_alpha(
                alpha_id="dup", run_id="r2", mode="SCALP", name="Dup2",
                thesis="t2", source="xgb", status=STATUS_ACTIVE,
                data_source=DATA_REAL, symbols=["ETHUSDT"],
            )

    def test_get_alpha(self, tmp_ledger: AlphaLedger) -> None:
        tmp_ledger.add_alpha(
            alpha_id="a1", run_id="r1", mode="SWING", name="A1",
            thesis="t", source="xgb", status=STATUS_ACTIVE,
            data_source=DATA_REAL, symbols=["BTCUSDT"],
        )
        found = tmp_ledger.get_alpha("a1")
        assert found is not None
        assert found["name"] == "A1"
        assert tmp_ledger.get_alpha("nonexistent") is None


class TestAlphaLedgerUpsert:
    def test_upsert_creates_new(self, tmp_ledger: AlphaLedger) -> None:
        entry = tmp_ledger.upsert_alpha(
            alpha_id="new_alpha",
            run_id="r1",
            mode="SCALP",
            name="New",
            net_R_per_trade=0.05,
        )
        assert entry["net_R_per_trade"] == 0.05
        assert len(tmp_ledger.alphas) == 1

    def test_upsert_updates_existing(self, tmp_ledger: AlphaLedger) -> None:
        tmp_ledger.add_alpha(
            alpha_id="u1", run_id="r1", mode="SCALP", name="U1",
            thesis="t", source="xgb", status=STATUS_ACTIVE,
            data_source=DATA_REAL, symbols=["BTCUSDT"],
            net_R_per_trade=0.01,
        )
        first_seen = tmp_ledger.get_alpha("u1")["date_first_seen"]
        tmp_ledger.upsert_alpha("u1", net_R_per_trade=0.05, status=STATUS_HOLD)
        entry = tmp_ledger.get_alpha("u1")
        assert entry["net_R_per_trade"] == 0.05
        assert entry["status"] == STATUS_HOLD
        assert entry["alpha_id"] == "u1"
        assert entry["date_first_seen"] == first_seen

    def test_upsert_preserves_first_seen(self, tmp_ledger: AlphaLedger) -> None:
        tmp_ledger.upsert_alpha("fs1", run_id="r1", mode="SCALP")
        first_seen = tmp_ledger.get_alpha("fs1")["date_first_seen"]
        tmp_ledger.upsert_alpha("fs1", net_R_per_trade=0.10)
        assert tmp_ledger.get_alpha("fs1")["date_first_seen"] == first_seen


class TestAlphaLedgerFilter:
    def _seed(self, ledger: AlphaLedger) -> None:
        ledger.add_alpha(
            alpha_id="s1", run_id="r1", mode="SCALP", name="S1", thesis="t",
            source="xgb", status=STATUS_ACTIVE, data_source=DATA_REAL,
            symbols=["BTCUSDT"],
        )
        ledger.add_alpha(
            alpha_id="w1", run_id="r1", mode="SWING", name="W1", thesis="t",
            source="factor_sprint", status=STATUS_REJECTED, data_source=DATA_REAL,
            symbols=["ETHUSDT"],
        )
        ledger.add_alpha(
            alpha_id="s2", run_id="r2", mode="SCALP", name="S2", thesis="t",
            source="discovery", status=STATUS_HOLD, data_source=DATA_SYNTHETIC,
            symbols=["SOLUSDT"],
        )

    def test_list_by_mode(self, tmp_ledger: AlphaLedger) -> None:
        self._seed(tmp_ledger)
        scalp = tmp_ledger.list_alphas(mode="SCALP")
        assert len(scalp) == 2
        swing = tmp_ledger.list_alphas(mode="SWING")
        assert len(swing) == 1

    def test_list_by_status(self, tmp_ledger: AlphaLedger) -> None:
        self._seed(tmp_ledger)
        active = tmp_ledger.list_alphas(status=STATUS_ACTIVE)
        assert len(active) == 1
        rejected = tmp_ledger.list_alphas(status=STATUS_REJECTED)
        assert len(rejected) == 1

    def test_list_by_source(self, tmp_ledger: AlphaLedger) -> None:
        self._seed(tmp_ledger)
        xgb = tmp_ledger.list_alphas(source="xgb")
        assert len(xgb) == 1


class TestAlphaLedgerPersistence:
    def test_write_and_reload(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.json"
        ledger1 = AlphaLedger(ledger_path=path)
        ledger1.add_alpha(
            alpha_id="p1", run_id="r1", mode="SCALP", name="P1", thesis="t",
            source="xgb", status=STATUS_ACTIVE, data_source=DATA_REAL,
            symbols=["BTCUSDT"], net_R_per_trade=0.05,
        )
        ledger1.write()

        ledger2 = AlphaLedger(ledger_path=path)
        assert len(ledger2.alphas) == 1
        assert ledger2.get_alpha("p1")["net_R_per_trade"] == 0.05

    def test_write_json_structure(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.json"
        ledger = AlphaLedger(ledger_path=path)
        ledger.add_alpha(
            alpha_id="j1", run_id="r1", mode="SCALP", name="J1", thesis="t",
            source="xgb", status=STATUS_ACTIVE, data_source=DATA_REAL,
            symbols=["BTCUSDT"],
        )
        ledger.write()
        data = json.loads(path.read_text())
        assert "ledger_version" in data
        assert "alphas" in data
        assert len(data["alphas"]) == 1


class TestAlphaLedgerCSV:
    def test_to_csv(self, tmp_ledger: AlphaLedger) -> None:
        tmp_ledger.add_alpha(
            alpha_id="c1", run_id="r1", mode="SCALP", name="C1", thesis="t",
            source="xgb", status=STATUS_ACTIVE, data_source=DATA_REAL,
            symbols=["BTCUSDT"], net_R_per_trade=0.05, tags=["watch"],
        )
        csv = tmp_ledger.to_csv()
        assert "alpha_id" in csv
        assert "c1" in csv
        assert "watch" in csv


class TestAlphaLedgerSummary:
    def test_summary(self, tmp_ledger: AlphaLedger) -> None:
        tmp_ledger.add_alpha(
            alpha_id="a1", run_id="r1", mode="SCALP", name="A1", thesis="t",
            source="xgb", status=STATUS_ACTIVE, data_source=DATA_REAL,
            symbols=["BTCUSDT"], net_R_per_trade=0.05,
        )
        tmp_ledger.add_alpha(
            alpha_id="a2", run_id="r1", mode="SWING", name="A2", thesis="t",
            source="xgb", status=STATUS_REJECTED, data_source=DATA_REAL,
            symbols=["ETHUSDT"], net_R_per_trade=-0.10,
        )
        s = tmp_ledger.summary
        assert s["total_alphas"] == 2
        assert s["by_status"] == {"ACTIVE": 1, "REJECTED": 1}
        assert s["by_mode"] == {"SCALP": 1, "SWING": 1}
        assert s["best_net_R"] == 0.05
