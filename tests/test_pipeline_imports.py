"""#317: Pipeline import smoke test — validates all import paths used by cli/v7_pipeline.py.

All imports tested here are consumed by the production pipeline entrypoint
(cli/v7_pipeline.py).  If any of these fail, the pipeline crashes at startup
regardless of data or configuration.

See: https://github.com/ddawnlll/v7-engine/issues/317
"""


def test_import_simulation_engine() -> None:
    """Simulation engine + contracts must import cleanly."""
    from simulation.engine.engine import simulate
    from simulation.contracts.models import (
        Candle,
        FundingEvent,
        FuturePath,
        SimulationInput,
        SimulationOutput,
        SimulationProfile,
        TradingMode,
    )
    assert simulate is not None


def test_import_label_adapter() -> None:
    """Label adapter bridges simulation output → training labels."""
    from alphaforge.labels.adapter import LabelAdapter
    assert LabelAdapter is not None


def test_import_mode_profiles() -> None:
    """Canonical mode profiles from alphaforge.modes."""
    from alphaforge.modes import CANONICAL_PROFILES, get_profile
    assert len(CANONICAL_PROFILES) >= 3


def test_import_feature_pipeline() -> None:
    """Core feature computation entrypoint (the import that #317 reported broken)."""
    from alphaforge.features.pipeline import compute_features
    assert callable(compute_features)


def test_import_training_modules() -> None:
    """XGBoost trainer + validation modules."""
    from alphaforge.training.xgb_trainer import XGBoostTrainer
    from alphaforge.validation.walk_forward_runner import (
        run_walk_forward,
        generate_directional_r_from_ohlcv,
    )
    assert XGBoostTrainer is not None
    assert callable(run_walk_forward)


def test_import_lib_market_data() -> None:
    """Market data services for backfill."""
    from lib.market_data.binance.klines_service import KlinesService
    from lib.market_data.binance.funding_service import FundingService
    from lib.market_data.binance.market_data_service import BinanceMarketDataService
    from lib.market_data.storage import StorageWriter
    from lib.market_data.catalog import DataCatalog
    from lib.market_data.binance.backfill import BackfillOrchestrator
    from lib.market_data.binance.rate_limiter import BinanceRateLimiter
    from lib.market_data.binance.checkpoint import BackfillCheckpoint
    assert KlinesService is not None
    assert FundingService is not None


def test_import_config_training() -> None:
    """Centralized training config (the #319 fix)."""
    from lib.config_training import load_training_config, TrainingConfig
    cfg = load_training_config("SWING")
    assert cfg.stop_multiplier == 2.0
    assert cfg.target_multiplier == 3.0


def test_import_registry_backed_config() -> None:
    """Backward-compatible MODE_CONFIG from alphaforge.train (built from registry)."""
    from alphaforge.train import MODE_CONFIG
    assert MODE_CONFIG["SCALP"]["stop_mult"] == 1.75
    assert MODE_CONFIG["SCALP"]["target_mult"] == 1.75
    assert MODE_CONFIG["AGGRESSIVE_SCALP"]["stop_mult"] == 1.25
    assert MODE_CONFIG["AGGRESSIVE_SCALP"]["target_mult"] == 1.25
