"""
Tests for lib/market_data/binance/checkpoint.py
"""

import json
import os
import tempfile

import pytest

from lib.market_data.binance.checkpoint import BackfillCheckpoint


class TestBackfillCheckpoint:
    def test_save_and_load(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = f.name

        try:
            cp = BackfillCheckpoint(file_path=tmp_path)
            cp.save("BTCUSDT", "1h", 1000, 2000, [{"start": 1000, "end": 2000}])

            data = cp.load()
            assert "BTCUSDT_1h" in data
            entry = data["BTCUSDT_1h"]
            assert entry["symbol"] == "BTCUSDT"
            assert entry["interval"] == "1h"
            assert entry["start_time"] == 1000
            assert entry["end_time"] == 2000
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_is_completed(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = f.name

        try:
            cp = BackfillCheckpoint(file_path=tmp_path)
            cp.save("BTCUSDT", "1h", 1000, 2000, [{"start": 1000, "end": 2000}])

            assert cp.is_completed("BTCUSDT", "1h", 1000, 2000)
            assert cp.is_completed("BTCUSDT", "1h", 1000, 1999)
            assert not cp.is_completed("BTCUSDT", "1h", 1000, 2001)
            assert not cp.is_completed("ETHUSDT", "1h", 1000, 2000)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_is_completed_exact_coverage(self):
        """is_completed returns True only if checkpoint range covers the query."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = f.name

        try:
            cp = BackfillCheckpoint(file_path=tmp_path)
            cp.save("BTCUSDT", "1h", 1000, 5000, [{"start": 1000, "end": 5000}])

            # Query inside the range
            assert cp.is_completed("BTCUSDT", "1h", 1500, 3000)
            # Query exactly matching
            assert cp.is_completed("BTCUSDT", "1h", 1000, 5000)
            # Query extending beyond
            assert not cp.is_completed("BTCUSDT", "1h", 1000, 5001)
            assert not cp.is_completed("BTCUSDT", "1h", 999, 5000)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_is_completed_missing_file(self):
        cp = BackfillCheckpoint(file_path="/nonexistent/path/checkpoint.json")
        assert not cp.is_completed("BTCUSDT", "1h", 1000, 2000)

    def test_remove_entry(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = f.name

        try:
            cp = BackfillCheckpoint(file_path=tmp_path)
            cp.save("BTCUSDT", "1h", 1000, 2000, [{"start": 1000, "end": 2000}])
            assert cp.is_completed("BTCUSDT", "1h", 1000, 2000)

            cp.remove("BTCUSDT", "1h")
            assert not cp.is_completed("BTCUSDT", "1h", 1000, 2000)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_load_nonexistent_file(self):
        cp = BackfillCheckpoint(file_path="/tmp/__nonexistent_checkpoint.json")
        data = cp.load()
        assert data == {}

    def test_load_corrupt_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json")
            tmp_path = f.name

        try:
            cp = BackfillCheckpoint(file_path=tmp_path)
            data = cp.load()
            assert data == {}
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_multiple_symbols(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp_path = f.name

        try:
            cp = BackfillCheckpoint(file_path=tmp_path)
            cp.save("BTCUSDT", "1h", 1000, 2000, [{"start": 1000, "end": 2000}])
            cp.save("ETHUSDT", "4h", 3000, 4000, [{"start": 3000, "end": 4000}])

            data = cp.load()
            assert len(data) == 2
            assert cp.is_completed("BTCUSDT", "1h", 1000, 2000)
            assert cp.is_completed("ETHUSDT", "4h", 3000, 4000)
            assert not cp.is_completed("BTCUSDT", "4h", 1000, 2000)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_make_key_uppercases(self):
        """_make_key should uppercase the symbol."""
        cp = BackfillCheckpoint(file_path="/tmp/test.json")
        key = cp._make_key("btcusdt", "1h")
        assert key == "BTCUSDT_1h"
