"""
Tests for lib/market_data/catalog.py
"""

import os
import tempfile

import pytest

from lib.market_data.catalog import DataCatalog


class TestDataCatalog:
    def test_add_entry(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            catalog_path = os.path.join(tmp_dir, "catalog.json")
            catalog = DataCatalog(catalog_path=catalog_path)

            catalog.add_entry("BTCUSDT", "1h", 1000, 2000, 100, "abc123")
            assert len(catalog._entries) == 1
            assert catalog._entries[0]["symbol"] == "BTCUSDT"
            assert catalog._entries[0]["row_count"] == 100

    def test_add_entry_uppercases_symbol(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            catalog_path = os.path.join(tmp_dir, "catalog.json")
            catalog = DataCatalog(catalog_path=catalog_path)

            catalog.add_entry("btcusdt", "1h", 1000, 2000, 100, "abc123")
            assert catalog._entries[0]["symbol"] == "BTCUSDT"

    def test_query_all(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            catalog_path = os.path.join(tmp_dir, "catalog.json")
            catalog = DataCatalog(catalog_path=catalog_path)

            catalog.add_entry("BTCUSDT", "1h", 1000, 2000, 100, "abc")
            catalog.add_entry("ETHUSDT", "1h", 1000, 2000, 200, "def")

            results = catalog.query()
            assert len(results) == 2

    def test_query_by_symbol(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            catalog_path = os.path.join(tmp_dir, "catalog.json")
            catalog = DataCatalog(catalog_path=catalog_path)

            catalog.add_entry("BTCUSDT", "1h", 1000, 2000, 100, "abc")
            catalog.add_entry("ETHUSDT", "1h", 1000, 2000, 200, "def")

            results = catalog.query(symbol="BTCUSDT")
            assert len(results) == 1
            assert results[0]["symbol"] == "BTCUSDT"

    def test_query_by_interval(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            catalog_path = os.path.join(tmp_dir, "catalog.json")
            catalog = DataCatalog(catalog_path=catalog_path)

            catalog.add_entry("BTCUSDT", "1h", 1000, 2000, 100, "abc")
            catalog.add_entry("BTCUSDT", "4h", 1000, 2000, 50, "def")

            results = catalog.query(interval="1h")
            assert len(results) == 1
            assert results[0]["interval"] == "1h"

    def test_query_by_time_range(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            catalog_path = os.path.join(tmp_dir, "catalog.json")
            catalog = DataCatalog(catalog_path=catalog_path)

            catalog.add_entry("BTCUSDT", "1h", 1000, 2000, 100, "abc")
            catalog.add_entry("BTCUSDT", "1h", 3000, 4000, 100, "def")

            results = catalog.query(start_ts=2000)
            assert len(results) == 1
            assert results[0]["start_ts"] == 3000

    def test_query_multiple_filters(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            catalog_path = os.path.join(tmp_dir, "catalog.json")
            catalog = DataCatalog(catalog_path=catalog_path)

            catalog.add_entry("BTCUSDT", "1h", 1000, 2000, 100, "abc")
            catalog.add_entry("BTCUSDT", "4h", 1000, 2000, 50, "def")
            catalog.add_entry("ETHUSDT", "1h", 1000, 2000, 200, "ghi")

            results = catalog.query(symbol="BTCUSDT", interval="1h")
            assert len(results) == 1

    def test_save_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            catalog_path = os.path.join(tmp_dir, "catalog.json")
            catalog = DataCatalog(catalog_path=catalog_path)

            catalog.add_entry("BTCUSDT", "1h", 1000, 2000, 100, "abc")
            catalog.save()

            # Create a new catalog instance pointing to the same file
            catalog2 = DataCatalog(catalog_path=catalog_path)
            results = catalog2.query()
            assert len(results) == 1
            assert results[0]["symbol"] == "BTCUSDT"

    def test_clear(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            catalog_path = os.path.join(tmp_dir, "catalog.json")
            catalog = DataCatalog(catalog_path=catalog_path)

            catalog.add_entry("BTCUSDT", "1h", 1000, 2000, 100, "abc")
            assert len(catalog.query()) == 1

            catalog.clear()
            assert len(catalog.query()) == 0

    def test_load_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            catalog_path = os.path.join(tmp_dir, "nonexistent.json")
            catalog = DataCatalog(catalog_path=catalog_path)
            assert catalog.query() == []

    def test_load_corrupt_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            catalog_path = os.path.join(tmp_dir, "catalog.json")
            with open(catalog_path, "w") as f:
                f.write("corrupt data")

            catalog = DataCatalog(catalog_path=catalog_path)
            assert catalog.query() == []

    def test_entries_have_ingested_at(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            catalog_path = os.path.join(tmp_dir, "catalog.json")
            catalog = DataCatalog(catalog_path=catalog_path)

            catalog.add_entry("BTCUSDT", "1h", 1000, 2000, 100, "abc")
            assert "ingested_at" in catalog._entries[0]
            assert isinstance(catalog._entries[0]["ingested_at"], str)

    def test_query_missing_symbol(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            catalog_path = os.path.join(tmp_dir, "catalog.json")
            catalog = DataCatalog(catalog_path=catalog_path)

            catalog.add_entry("BTCUSDT", "1h", 1000, 2000, 100, "abc")
            results = catalog.query(symbol="NONEXISTENT")
            assert results == []
