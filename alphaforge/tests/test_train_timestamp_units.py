"""Timestamp unit canonicalization at the AlphaForge real-data boundary."""

from __future__ import annotations

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from alphaforge.train import load_cached_data


def test_data_lake_millisecond_timestamps_become_nanoseconds(tmp_path):
    path = tmp_path / "raw" / "BTCUSDT"
    path.mkdir(parents=True)
    pq.write_table(
        pa.table({
            "timestamp": [1_700_000_000_000, 1_700_000_003_600],
            "open": [1.0, 1.1], "high": [1.2, 1.3],
            "low": [0.9, 1.0], "close": [1.1, 1.2], "volume": [2.0, 3.0],
        }),
        path / "BTCUSDT_1h.parquet",
    )
    data = load_cached_data(["BTCUSDT"], "1h", str(tmp_path))
    assert data is not None
    assert data["timestamp"].dtype == np.int64
    assert data["timestamp"].tolist() == [1_700_000_000_000_000_000, 1_700_000_003_600_000_000]
