"""Configuration for alpha thesis validation."""

from dataclasses import dataclass, field
from typing import List

# ── Paths ────────────────────────────────────────────────────────────────────
RAW_DATA_DIR = "data/raw"
CACHE_DIR = "data/cache"
RESULTS_DIR = "results"

# ── Time Range ───────────────────────────────────────────────────────────────
START_DATE = "2021-01-01"
END_DATE = "2024-12-31"
TRAIN_START = "2021-07-01"  # first 6 months for initial training

# ── Universe ─────────────────────────────────────────────────────────────────
TOP_N_SYMBOLS = 60  # top 60 by volume
MIN_DATA_PCT = 0.90  # drop symbols with < 90% data completeness

# ── Walk-Forward ─────────────────────────────────────────────────────────────
N_FOLDS = 12
TRAIN_WINDOW_MONTHS = 6
OOS_START = "2022-01-01"
BOOTSTRAP_SAMPLES = 100

# ── Transaction Costs ────────────────────────────────────────────────────────
MAKER_FEE = 0.0005  # 0.05%
TAKER_FEE = 0.001   # 0.1%
SLIPPAGE_TIER1 = 0.001  # 0.1%
SLIPPAGE_TIER2 = 0.003  # 0.3%
SLIPPAGE_TIER3 = 0.005  # 0.5%

# Liquidity tiers for slippage (by volume rank)
TIER1_CUTOFF = 10   # top 10 symbols
TIER2_CUTOFF = 40   # next 30 symbols

# ── Exit Rules (Fixed) ───────────────────────────────────────────────────────
STOP_LOSS_PCT = 0.02   # 2%
TAKE_PROFIT_PCT = 0.04  # 4% (2R)

ALTCOIN_DELAY_MAX_HOLD_H = 24
VOLATILITY_COMPRESSION_MAX_HOLD_H = 48
FUNDING_DIVERGENCE_MAX_HOLD_H = 12

# ── Hypothesis 1: Altcoin Delay ──────────────────────────────────────────────
ALTCOIN_DELAY_BTC_THRESHOLDS = [0.02, 0.03, 0.04, 0.05]
ALTCOIN_DELAY_WINDOWS_H = [1, 2, 4]
ALTCOIN_DELAY_UNIVERSE_SIZES = [10, 20, 40]

# ── Hypothesis 2: Volatility Compression ─────────────────────────────────────
VOLATILITY_COMPRESSION_THRESHOLDS = [0.40, 0.50, 0.60]
VOLATILITY_COMPRESSION_DURATIONS_H = [48, 72, 96]
VOLATILITY_COMPRESSION_ATR_PERIODS = [14, 20, 28]

# ── Hypothesis 3: Funding Divergence ─────────────────────────────────────────
FUNDING_DIVERGENCE_FUNDING_THRESHOLDS = [0.0005, 0.001, 0.0015, 0.002]
FUNDING_DIVERGENCE_SPOT_THRESHOLDS = [0.0, 0.005, 0.01]
FUNDING_DIVERGENCE_HOLD_DURATIONS_H = [4, 8, 12]

# ── Hypothesis 4: Open Interest Spike ────────────────────────────────────────
OPEN_INTEREST_SPIKE_THRESHOLDS = [0.15, 0.20, 0.25, 0.30]
OPEN_INTEREST_SPIKE_LOOKBACK_H = [4, 8, 12]
OPEN_INTEREST_SPIKE_PRICE_THRESHOLDS = [0.005, 0.01, 0.02]  # 0.5%, 1%, 2%
OPEN_INTEREST_SPIKE_MAX_HOLD_H = 24

# ── Hypothesis 5: Volume Anomaly ─────────────────────────────────────────────
VOLUME_ANOMALY_MULTIPLES = [2.0, 3.0, 4.0, 5.0]
VOLUME_ANOMALY_LOOKBACK = [10, 20, 30]  # bars
VOLUME_ANOMALY_PRICE_THRESHOLDS = [0.005, 0.01, 0.02]
VOLUME_ANOMALY_MAX_HOLD_H = 24

# ── Regime Detection ────────────────────────────────────────────────────────
TREND_MA_PERIOD = 50
TREND_THRESHOLD = 0.02  # price vs MA > 2% = trending

# ── Composite ────────────────────────────────────────────────────────────────
MAX_CORRELATION = 0.6  # reject composite if hypotheses too correlated

# ── Symbols for universe selection ──────────────────────────────────────────
# Canonical list from the reusable data layer (imported absolutely)
from data.config import FALLBACK_SYMBOLS as PERPETUAL_SYMBOLS

# Symbols delisted from Binance futures between 2021-2024 (anti-survivorship)
# Including these ensures we don't overfit to coins that survived.
KNOWN_DELISTED = {
    # Terra collapse May 2022
    "LUNAUSDT", "LUNA2USDT", "USTUSDT",
    # FTX collapse Nov 2022
    "FTTUSDT", "SRMUSDT", "RAYUSDT", "MAPSUSDT", "FIDAUSDT",
    # Celsius bankruptcy Jul 2022
    "CELSIUSUSDT",
    # Delisted for low volume / regulatory
    "YFIIUSDT", "BTSUSDT", "PERLUSDT", "TROYUSDT", "DOCKUSDT",
    "COCOSUSDT", "UNFIUSDT", "REEFUSDT", "DODOUSDT", "BAKEUSDT",
    "ALPACAUSDT", "BADGERUSDT", "FISUSDT", "PROSUSDT", "VITEUSDT",
    "AKROUSDT", "CTKUSDT", "BTCSTUSDT", "AUTOUSDT", "TVKUSDT",
    "PNTUSDT", "BURGERUSDT", "SUTERUSDT", "CHESSUSDT", "TCTUSDT",
}

REALISTIC_COST_MODEL = False  # set True to apply fees + slippage per trade

# Estimated volume ranks (1 = highest) for slippage tiers
# Used when Binance 24h ticker API is unavailable
ESTIMATED_TIER_1 = {
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT",
}
ESTIMATED_TIER_2 = {
    "MATICUSDT", "UNIUSDT", "SHIBUSDT", "LTCUSDT", "ATOMUSDT",
    "ETCUSDT", "XLMUSDT", "BCHUSDT", "ALGOUSDT", "TRXUSDT",
    "NEARUSDT", "FILUSDT", "APTUSDT", "ARBUSDT", "OPUSDT",
    "ICPUSDT", "SUIUSDT", "PEPEUSDT", "INJUSDT", "TIAUSDT",
    "SEIUSDT", "TONUSDT", "RUNEUSDT", "AAVEUSDT", "FTMUSDT",
    "EGLDUSDT", "AXSUSDT", "SANDUSDT", "MANAUSDT", "CRVUSDT",
    "EOSUSDT", "KAVAUSDT", "GALAUSDT", "ENJUSDT", "ZECUSDT",
    "DASHUSDT", "COMPUSDT", "SUSHIUSDT", "YFIUSDT", "SNXUSDT",
}
# Everything else falls into TIER_3 (deepest slippage)

# ── Regime Filter ────────────────────────────────────────────────────────────
BLOCKED_REGIMES = {"TRANSITION"}  # signals in these regimes are skipped
