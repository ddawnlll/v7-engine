"""
Test suite for lib/ — validates import boundary, correctness of primitives,
and that nothing from v7 or alphaforge leaks into lib.
"""

import sys
import pytest

# =====================================================================
# HARD STOP: lib_import_boundary_violation
# lib/ must NOT import v7.* or alphaforge.*
# =====================================================================


def _get_all_lib_module_names() -> list[str]:
    """Discover all lib submodules by importing lib and walking subpackages."""
    import lib  # noqa: F401 — ensure lib is importable
    import pkgutil
    import lib as lib_root

    def walk(pkg, prefix: str) -> list[str]:
        modules = []
        for _importer, modname, is_pkg in pkgutil.walk_packages(
            pkg.__path__, prefix=prefix,
        ):
            if is_pkg:
                # Full module name
                modules.append(modname)
                # Recurse
                try:
                    __import__(modname)
                    sub = sys.modules[modname]
                    modules.extend(walk(sub, f"{modname}."))
                except ImportError:
                    pass
            else:
                modules.append(modname)
        return modules

    return walk(lib_root, "lib.")


def test_lib_does_not_import_v7_or_alphaforge():
    """HARD STOP: lib_import_boundary_violation.

    No lib/ module may import anything from v7 or alphaforge.
    """
    import lib  # noqa: F401

    # Load all lib modules
    module_names = _get_all_lib_module_names()
    for name in module_names:
        try:
            mod = __import__(name)
        except ImportError as e:
            # Some modules may have missing dependencies (requests), skip
            print(f"  skipping {name}: {e}")
            continue

        # Check what the module imports
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            mod_name = getattr(attr, "__module__", "") or getattr(attr, "__name__", "")
            if mod_name.startswith("v7."):
                pytest.fail(
                    f"LIB IMPORT BOUNDARY VIOLATION: {name} imports {mod_name} "
                    f"via '{attr_name}'"
                )
            if mod_name.startswith("alphaforge.") or mod_name.startswith("alphaforge"):
                pytest.fail(
                    f"LIB IMPORT BOUNDARY VIOLATION: {name} imports {mod_name} "
                    f"via '{attr_name}'"
                )


# =====================================================================
# Contracts
# =====================================================================

def test_kline_record_creation():
    from lib.market_data.contracts import KlineRecord
    r = KlineRecord(
        symbol="BTCUSDT",
        timestamp=1234567890000,
        open=50000.0, high=51000.0, low=49000.0, close=50500.0,
        volume=100.0, quote_volume=5_000_000.0,
        trade_count=1000, taker_buy_volume=55.0, taker_buy_quote_volume=2_750_000.0,
        interval="1h", source="binance", is_closed=True,
    )
    assert r.symbol == "BTCUSDT"
    assert r.close == 50500.0


# =====================================================================
# Quality
# =====================================================================

def test_detect_gaps():
    from lib.market_data.quality import detect_gaps
    from lib.market_data.contracts import KlineRecord

    base_ts = 1_000_000_000_000
    gap_ms = 60 * 60_000  # 1h
    records = [
        KlineRecord(symbol="T", timestamp=base_ts, open=1, high=2, low=1, close=1.5,
                     volume=10, quote_volume=15, trade_count=10,
                     taker_buy_volume=5, taker_buy_quote_volume=7.5,
                     interval="1h", source="binance", is_closed=True),
        KlineRecord(symbol="T", timestamp=base_ts + gap_ms + 120_000, open=1, high=2, low=1,
                     close=1.5, volume=10, quote_volume=15, trade_count=10,
                     taker_buy_volume=5, taker_buy_quote_volume=7.5,
                     interval="1h", source="binance", is_closed=True),
    ]
    gaps = detect_gaps(records, 60)
    assert len(gaps) == 1
    assert gaps[0][0] == base_ts + gap_ms  # expected start of gap
    assert gaps[0][1] == base_ts + gap_ms + 120_000  # actual next timestamp


def test_detect_duplicates():
    from lib.market_data.quality import detect_duplicates
    from lib.market_data.contracts import KlineRecord

    base_ts = 1_000_000_000_000
    rec = lambda ts: KlineRecord(symbol="T", timestamp=ts, open=1, high=2, low=1,
                                  close=1.5, volume=10, quote_volume=15,
                                  trade_count=10, taker_buy_volume=5,
                                  taker_buy_quote_volume=7.5,
                                  interval="1h", source="binance", is_closed=True)
    records = [rec(base_ts), rec(base_ts), rec(base_ts + 60_000)]
    dups = detect_duplicates(records)
    assert dups == [1]  # index 1 is duplicate


# =====================================================================
# Indicators
# =====================================================================

def test_compute_atr():
    from lib.indicators.atr import compute_atr
    highs = [10, 12, 11, 13, 14, 12, 15]
    lows = [8, 9, 8, 10, 11, 9, 12]
    closes = [9, 11, 10, 12, 13, 11, 14]
    atr = compute_atr(highs, lows, closes, period=3)
    assert len(atr) == len(highs)
    assert all(v is None or (isinstance(v, float) and (v == v)) or v != v for v in atr)  # nan-safe
    # First 3 values should be NaN
    assert atr[0] != atr[0]  # nan
    assert atr[1] != atr[1]  # nan
    assert atr[2] != atr[2]  # nan
    # ATR from index 3 should be a finite positive number
    assert atr[3] > 0


def test_log_returns():
    from lib.indicators.returns import log_returns
    prices = [100.0, 105.0, 102.0]
    rets = log_returns(prices)
    assert len(rets) == 3
    assert rets[0] != rets[0]  # NaN
    assert rets[1] > 0  # positive return
    assert rets[2] < 0  # negative return


def test_simple_returns():
    from lib.indicators.returns import simple_returns
    prices = [100.0, 105.0, 102.0]
    rets = simple_returns(prices)
    assert len(rets) == 3
    assert rets[0] != rets[0]  # NaN
    assert rets[1] == 0.05


def test_rolling_std():
    from lib.indicators.volatility import rolling_std
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    stds = rolling_std(values, period=3)
    assert len(stds) == 10
    assert stds[0] != stds[0]  # NaN
    assert stds[1] != stds[1]  # NaN
    assert stds[2] == pytest.approx(0.81649658, rel=1e-5)


def test_parkinson_vol():
    from lib.indicators.volatility import parkinson_vol
    highs = [10, 11, 12, 11, 13]
    lows = [8, 9, 10, 9, 10]
    vols = parkinson_vol(highs, lows, period=3)
    assert len(vols) == 5
    assert vols[0] != vols[0]  # NaN
    assert vols[1] != vols[1]  # NaN
    assert vols[2] > 0


def test_rolling_apply():
    from lib.indicators.rolling import rolling_apply
    values = [1, 2, 3, 4, 5]
    sums = rolling_apply(values, 3, lambda w: sum(w))
    assert len(sums) == 5
    assert sums[0] is None
    assert sums[1] is None
    assert sums[2] == 6
    assert sums[3] == 9
    assert sums[4] == 12


# =====================================================================
# Costs
# =====================================================================

def test_estimate_fee():
    from lib.costs.fees import estimate_fee, estimate_maker_fee, estimate_taker_fee
    notional = 10_000.0
    assert estimate_maker_fee(notional) == 1.0   # 0.01% = $1
    assert estimate_taker_fee(notional) == 4.0   # 0.04% = $4
    assert estimate_fee(notional, "maker") == 1.0
    assert estimate_fee(notional, "taker", taker_rate=0.0005) == 5.0


def test_get_slippage():
    from lib.costs.slippage import get_slippage
    slippage = get_slippage(10_000.0, 100_000.0)
    assert slippage > 0
    assert isinstance(slippage, float)

    # Explicit percentage
    explicit = get_slippage(10_000.0, 100_000.0, slippage_pct=0.05)
    assert explicit == 5.0  # 0.05% of 10k


# =====================================================================
# Time
# =====================================================================

def test_interval_to_minutes():
    from lib.time.intervals import interval_to_minutes
    assert interval_to_minutes("1m") == 1
    assert interval_to_minutes("1h") == 60
    assert interval_to_minutes("4h") == 240
    assert interval_to_minutes("1d") == 1440


def test_validate_interval():
    from lib.time.intervals import validate_interval
    assert validate_interval("1h")
    assert not validate_interval("invalid")


def test_generate_folds_basic():
    from lib.time.folds import generate_folds
    ms_per_day = 86_400_000
    start = 1_000_000_000_000
    end = start + 500 * ms_per_day  # 500 days of data
    folds = generate_folds(start, end, train_window_days=365, val_window_days=60)
    assert len(folds) >= 1
    assert folds[0].fold_id == 0
    assert folds[0].train_start == start
    assert folds[0].val_end <= end


def test_generate_folds_too_short():
    from lib.time.folds import generate_folds
    import pytest as _pytest
    ms_per_day = 86_400_000
    start = 1_000_000_000_000
    end = start + 30 * ms_per_day  # only 30 days
    with _pytest.raises(ValueError, match="too short"):
        generate_folds(start, end, train_window_days=365, val_window_days=60)
