# Derivatives Data Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire real Open Interest, Premium Index, and Funding Rate data into the AlphaForge feature pipeline so existing feature code (open_interest.py, premium_index.py, funding.py) produces real signals instead of NaN/empty-dict.

**Architecture:** Three-layer: (1) BinanceClient gets new API methods, (2) new Service classes normalize/paginate, (3) AlphaForge train.py feeds data into the ohlcv_data dict that feature pipeline.py reads. Existing feature code needs ZERO changes — it activates automatically when the right keys appear in ohlcv_data.

**Tech Stack:** Python 3.11+, numpy, requests, existing lib/market_data patterns

## Global Constraints

- All new code must follow existing patterns in lib/market_data/binance/ (FundingService is the template)
- BinanceClient stays HTTP-only: no caching, no normalization, no business logic
- Feature code in alphaforge/features/ is NOT modified — only data feeding changes
- All timestamps are Unix milliseconds (int64)
- 1h bar resolution for open interest (hourly); 8h for funding rate (forward-filled); 1h for premium index

---

### Task 1: Add BinanceClient API methods for open interest and premium index

**Files:**
- Modify: `lib/market_data/binance/client.py` — add `get_open_interest_hist()` and `get_premium_index_klines()`

**Interfaces:**
- Consumes: Binance REST API endpoints `/fapi/v1/openInterestHist` and `/fapi/v1/premiumIndexKlines`
- Produces: two new public methods on BinanceClient following exact pattern of existing `get_funding_rate()`

- [ ] **Step 1: Add `get_open_interest_hist()` method**

Insert after `get_funding_rate()` (line 109 in client.py):

```python
    def get_open_interest_hist(
        self,
        symbol: str,
        period: str = "1h",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500,
    ) -> list[list[Any]]:
        """Fetch open interest history from Binance Futures.

        Returns raw response data. Use OpenInterestService for normalization.
        Period is aggregation interval: "5m","15m","30m","1h","2h","4h","6h","12h","1d".
        Max limit per call is 500.
        """
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "period": period,
            "limit": min(limit, 500),
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        return self._get("/fapi/v1/openInterestHist", params)

    def get_premium_index_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
    ) -> list[list[Any]]:
        """Fetch premium index klines from Binance Futures.

        Returns raw response data. Use PremiumIndexService for normalization.
        Premium index klines show the premium/discount of the mark price vs index price.
        """
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": min(limit, 1000),
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        return self._get("/fapi/v1/premiumIndexKlines", params)
```

- [ ] **Step 2: Commit**

```bash
git add lib/market_data/binance/client.py
git commit -m "feat: add get_open_interest_hist and get_premium_index_klines to BinanceClient"
```

---

### Task 2: Create OpenInterestService

**Files:**
- Create: `lib/market_data/binance/open_interest_service.py`
- Test: `lib/tests/test_open_interest_service.py`

- [ ] **Step 1: Write failing test**

Create `lib/tests/test_open_interest_service.py`:

```python
"""Tests for OpenInterestService."""
from lib.market_data.binance.open_interest_service import OpenInterestService, OpenInterestRecord

class _FakeClient:
    def get_open_interest_hist(self, symbol="BTCUSDT", period="1h",
                                start_time=None, end_time=None, limit=500):
        return [[1700000000000, "BTCUSDT", 50000.0, 45000.0, 1234.5]]

def test_fetch_returns_records():
    service = OpenInterestService(_FakeClient())
    records = service.fetch("BTCUSDT", start_time=1700000000000, end_time=1700086400000)
    assert len(records) == 1
    assert isinstance(records[0], OpenInterestRecord)
    assert records[0].symbol == "BTCUSDT"
    assert records[0].timestamp == 1700000000000
    assert records[0].open_interest == 50000.0
    assert records[0].open_interest_value == 45000.0

def test_fetch_empty_on_no_data():
    class _EmptyClient:
        def get_open_interest_hist(self, **kwargs): return []
    service = OpenInterestService(_EmptyClient())
    records = service.fetch("BTCUSDT")
    assert records == []
```

- [ ] **Step 2: Create `open_interest_service.py`**

```python
"""Open Interest history service with time-range pagination."""
import logging
from dataclasses import dataclass
from typing import Optional
from lib.market_data.binance.client import BinanceClient

logger = logging.getLogger(__name__)

_PERIOD_MS = {"5m": 300_000, "15m": 900_000, "30m": 1_800_000,
              "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000,
              "6h": 21_600_000, "12h": 43_200_000, "1d": 86_400_000}
MAX_LIMIT = 500

@dataclass
class OpenInterestRecord:
    symbol: str
    timestamp: int
    open_interest: float
    open_interest_value: float

class OpenInterestService:
    def __init__(self, client: BinanceClient) -> None:
        self._client = client

    def fetch(self, symbol: str, period: str = "1h",
              start_time: Optional[int] = None,
              end_time: Optional[int] = None) -> list[OpenInterestRecord]:
        all_records = []
        current_start = start_time
        period_ms = _PERIOD_MS.get(period, 3_600_000)
        while True:
            raw = self._client.get_open_interest_hist(
                symbol=symbol, period=period,
                start_time=current_start, end_time=end_time, limit=MAX_LIMIT)
            chunk = [self._normalize(symbol, r) for r in raw]
            all_records.extend(chunk)
            if len(raw) < MAX_LIMIT:
                break
            last_ts = int(raw[-1][0])
            current_start = last_ts + period_ms
            if end_time is not None and current_start >= end_time:
                break
        return all_records

    @staticmethod
    def _normalize(symbol: str, raw: list) -> OpenInterestRecord:
        return OpenInterestRecord(
            symbol=symbol, timestamp=int(raw[0]),
            open_interest=float(raw[1]),
            open_interest_value=float(raw[2]))
```

- [ ] **Step 3: Run tests**

```bash
PYTHONPATH=. python3 -m pytest lib/tests/test_open_interest_service.py -v
```

Expected: 2 passed

- [ ] **Step 4: Commit**

```bash
git add lib/market_data/binance/open_interest_service.py lib/tests/test_open_interest_service.py
git commit -m "feat: add OpenInterestService with pagination"
```

---

### Task 3: Create PremiumIndexService

**Files:**
- Create: `lib/market_data/binance/premium_index_service.py`
- Test: `lib/tests/test_premium_index_service.py`

- [ ] **Step 1: Write failing test**

Create `lib/tests/test_premium_index_service.py`:

```python
"""Tests for PremiumIndexService."""
from lib.market_data.binance.premium_index_service import PremiumIndexService, PremiumIndexRecord

class _FakeClient:
    def get_premium_index_klines(self, symbol="BTCUSDT", interval="1h",
                                  start_time=None, end_time=None, limit=1000):
        return [[1700000000000, 100.5, 101.2, 99.8, 100.7, 50000.0]]

def test_fetch_returns_records():
    service = PremiumIndexService(_FakeClient())
    records = service.fetch("BTCUSDT", "1h", 1700000000000, 1700086400000)
    assert len(records) == 1
    assert records[0].symbol == "BTCUSDT"
    assert records[0].premium_close == 100.7
    assert records[0].index_price == 50000.0

def test_fetch_empty_on_no_data():
    class _EmptyClient:
        def get_premium_index_klines(self, **kwargs): return []
    service = PremiumIndexService(_EmptyClient())
    records = service.fetch("BTCUSDT", "1h")
    assert records == []
```

- [ ] **Step 2: Create `premium_index_service.py`**

```python
"""Premium Index klines service with time-range pagination."""
import logging
from dataclasses import dataclass
from typing import Optional
from lib.market_data.binance.client import BinanceClient
from lib.market_data.binance.klines_service import interval_to_minutes

logger = logging.getLogger(__name__)
MAX_LIMIT = 1000

@dataclass
class PremiumIndexRecord:
    symbol: str
    timestamp: int
    premium_open: float
    premium_high: float
    premium_low: float
    premium_close: float
    index_price: float

class PremiumIndexService:
    def __init__(self, client: BinanceClient) -> None:
        self._client = client

    def fetch(self, symbol: str, interval: str = "1h",
              start_time: Optional[int] = None,
              end_time: Optional[int] = None) -> list[PremiumIndexRecord]:
        all_records = []
        current_start = start_time
        step_ms = interval_to_minutes(interval) * 60_000
        while True:
            raw = self._client.get_premium_index_klines(
                symbol=symbol, interval=interval,
                start_time=current_start, end_time=end_time, limit=MAX_LIMIT)
            chunk = [self._normalize(symbol, r) for r in raw]
            all_records.extend(chunk)
            if len(raw) < MAX_LIMIT:
                break
            last_ts = int(raw[-1][0])
            current_start = last_ts + step_ms
            if end_time is not None and current_start >= end_time:
                break
        return all_records

    @staticmethod
    def _normalize(symbol: str, raw: list) -> PremiumIndexRecord:
        return PremiumIndexRecord(
            symbol=symbol, timestamp=int(raw[0]),
            premium_open=float(raw[1]), premium_high=float(raw[2]),
            premium_low=float(raw[3]), premium_close=float(raw[4]),
            index_price=float(raw[5]))
```

- [ ] **Step 3: Run tests**

```bash
PYTHONPATH=. python3 -m pytest lib/tests/test_premium_index_service.py -v
```

Expected: 2 passed

- [ ] **Step 4: Commit**

```bash
git add lib/market_data/binance/premium_index_service.py lib/tests/test_premium_index_service.py
git commit -m "feat: add PremiumIndexService with pagination"
```

---

### Task 4: Wire new services into BinanceMarketDataService

**Files:**
- Modify: `lib/market_data/binance/market_data_service.py`

- [ ] **Step 1: Add imports and constructor params**

Insert after existing imports:
```python
from lib.market_data.binance.open_interest_service import OpenInterestService, OpenInterestRecord
from lib.market_data.binance.premium_index_service import PremiumIndexService, PremiumIndexRecord
```

Update `__init__` (line 31-39):
```python
    def __init__(
        self,
        client: Optional[BinanceClient] = None,
        klines: Optional[KlinesService] = None,
        funding: Optional[FundingService] = None,
        open_interest: Optional[OpenInterestService] = None,
        premium_index: Optional[PremiumIndexService] = None,
    ) -> None:
        self._client = client or BinanceClient()
        self._klines = klines or KlinesService(self._client)
        self._funding = funding or FundingService(self._client)
        self._oi = open_interest or OpenInterestService(self._client)
        self._premium = premium_index or PremiumIndexService(self._client)
```

Add methods before the final newline:
```python
    def get_open_interest(
        self,
        symbol: str,
        period: str = "1h",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> list[OpenInterestRecord]:
        return self._oi.fetch(symbol, period, start_time, end_time)

    def get_premium_index(
        self,
        symbol: str,
        interval: str = "1h",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> list[PremiumIndexRecord]:
        return self._premium.fetch(symbol, interval, start_time, end_time)
```

- [ ] **Step 2: Commit**

```bash
git add lib/market_data/binance/market_data_service.py
git commit -m "feat: wire OI and premium index services into BinanceMarketDataService"
```

---

### Task 5: Feed derivatives data into AlphaForge feature pipeline

**Files:**
- Modify: `alphaforge/src/alphaforge/train.py` — add funding_rate, open_interest, premium_index to ohlcv_data dict

This activates the existing feature modules without changing them.

- [ ] **Step 1: Add synthetic derivatives data to `generate_synthetic_ohlcv()`**

Find the `all_data` dict initialization (around line 83), after the symbols loop add:
```python
    all_data["funding_rate"] = []
    all_data["open_interest"] = []
    all_data["premium_index"] = []
    for sym in symbols:
        all_data["funding_rate"].append(rng.randn(n_bars) * 0.001)
        all_data["open_interest"].append(1000.0 + rng.randn(n_bars) * 100.0)
        all_data["premium_index"].append(rng.randn(n_bars) * 0.5)
```

Find the `np.concatenate` block (around line 98-104), add:
```python
    all_data["funding_rate"] = np.concatenate(all_data["funding_rate"])
    all_data["open_interest"] = np.concatenate(all_data["open_interest"])
    all_data["premium_index"] = np.concatenate(all_data["premium_index"])
```

- [ ] **Step 2: Add derivatives to per-symbol ohlcv in `compute_features_selected()`**

In the per-symbol loop (line 431-437), after `"volume": ohlcv["volume"][mask]},` add:
```python
        if "funding_rate" in ohlcv:
            sym_ohlcv["funding_rate"] = ohlcv["funding_rate"][mask]
        if "open_interest" in ohlcv:
            sym_ohlcv["open_interest"] = ohlcv["open_interest"][mask]
        if "premium_index" in ohlcv:
            sym_ohlcv["premium_index"] = ohlcv["premium_index"][mask]
```

- [ ] **Step 3: Add derivatives to per-symbol ohlcv in `build_aligned_training_frame()`**

In the ohlcv_input dict (around line 523-530), after `"symbol": sym,` add:
```python
            if "funding_rate" in ohlcv:
                ohlcv_input["funding_rate"] = ohlcv["funding_rate"][mask]
            if "open_interest" in ohlcv:
                ohlcv_input["open_interest"] = ohlcv["open_interest"][mask]
            if "premium_index" in ohlcv:
                ohlcv_input["premium_index"] = ohlcv["premium_index"][mask]
```

- [ ] **Step 4: Run synthetic training to verify features activate**

```bash
PYTHONPATH=alphaforge/src:$PYTHONPATH python3 -m alphaforge.train --mode SWING --features all --n_bars 500 2>&1 | tail -30
```

Look for funding/OI/premium feature names in output.

- [ ] **Step 5: Commit**

```bash
git add alphaforge/src/alphaforge/train.py
git commit -m "feat: feed funding_rate, open_interest, premium_index into feature pipeline"
```

---

### Task 6: Add feature activation tests

**Files:**
- Modify: `alphaforge/tests/test_feature_pipeline.py` — add 3 test cases

- [ ] **Step 1: Add three test functions**

Edit `alphaforge/tests/test_feature_pipeline.py`, add at end:

```python
def test_funding_features_activate_with_real_data():
    from alphaforge.features.pipeline import compute_features
    import numpy as np
    n = 100
    ohlcv = {"open": np.full(n, 100.0), "high": np.full(n, 102.0),
             "low": np.full(n, 99.0), "close": 100.0 + np.cumsum(np.random.randn(n) * 0.5),
             "volume": np.full(n, 1000.0), "funding_rate": np.random.randn(n) * 0.001}
    fm = compute_features(ohlcv, mode="SWING", feature_groups=["PERPETUAL_FUNDING"])
    funding_keys = [k for k in fm.features if "funding" in k or "open_interest_proxy" in k]
    assert len(funding_keys) > 0
    for k in funding_keys:
        assert not np.all(np.isnan(fm.features[k])), f"{k} all NaN"

def test_open_interest_features_activate_with_real_data():
    from alphaforge.features.pipeline import compute_features
    import numpy as np
    n = 100
    ohlcv = {"open": np.full(n, 100.0), "high": np.full(n, 102.0),
             "low": np.full(n, 99.0), "close": 100.0 + np.cumsum(np.random.randn(n) * 0.5),
             "volume": np.full(n, 1000.0),
             "open_interest": 50000.0 + np.cumsum(np.random.randn(n) * 100)}
    fm = compute_features(ohlcv, mode="SWING", feature_groups=["OPEN_INTEREST"])
    oi_keys = [k for k in fm.features if "open_interest" in k]
    assert len(oi_keys) > 0
    for k in oi_keys:
        assert not np.all(np.isnan(fm.features[k])), f"{k} all NaN"

def test_premium_index_features_activate_with_real_data():
    from alphaforge.features.pipeline import compute_features
    import numpy as np
    n = 100
    ohlcv = {"open": np.full(n, 100.0), "high": np.full(n, 102.0),
             "low": np.full(n, 99.0), "close": 100.0 + np.cumsum(np.random.randn(n) * 0.5),
             "volume": np.full(n, 1000.0), "premium_index": np.random.randn(n) * 0.5}
    fm = compute_features(ohlcv, mode="SWING", feature_groups=["PREMIUM_INDEX"])
    basis_keys = [k for k in fm.features if "basis" in k]
    assert len(basis_keys) > 0
    for k in basis_keys:
        assert not np.all(np.isnan(fm.features[k])), f"{k} all NaN"
```

- [ ] **Step 2: Run tests**

```bash
PYTHONPATH=alphaforge/src:$PYTHONPATH python3 -m pytest alphaforge/tests/test_feature_pipeline.py::test_funding_features_activate_with_real_data alphaforge/tests/test_feature_pipeline.py::test_open_interest_features_activate_with_real_data alphaforge/tests/test_feature_pipeline.py::test_premium_index_features_activate_with_real_data -v
```

Expected: 3 passed

- [ ] **Step 3: Commit**

```bash
git add alphaforge/tests/test_feature_pipeline.py
git commit -m "test: verify funding/OI/premium features activate with real data"
```

---

### Task 7: Final end-to-end verification

- [ ] **Step 1: Run full synthetic training**

```bash
PYTHONPATH=alphaforge/src:$PYTHONPATH python3 -m alphaforge.train --mode SWING --features all --n_bars 1000 2>&1 | tee /tmp/train_output.txt
```

- [ ] **Step 2: Verify derivatives features are active**

```bash
echo "=== Funding/OI/Premium features ===" && grep -i "funding\|oi_proxy\|open_interest\|premium\|basis" /tmp/train_output.txt || echo "NONE FOUND"
```
