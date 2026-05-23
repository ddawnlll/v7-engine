# V7 Regime-Aware and Market Reality Extensions

**Status:** Design Document  
**Version:** 1.0  
**Last Updated:** 2026-01-XX  
**Purpose:** Define all architectural extensions required for V7 to achieve real-market viability

---

## 1. Executive Summary

This document defines the extensions to the base V7 architecture that address the critical gaps identified during design review:

1. **Regime detection and routing** — system must know market regime before making decisions
2. **Mode-specific regime detection** — each trading mode operates in different timeframes with different regime definitions
3. **Regime-aware labels** — labels must include regime context
4. **Regime-aware evaluation** — walk-forward must test regime transitions
5. **Online adaptation** — system must adapt to changing market conditions
6. **Symbol-specific parameters** — different symbols have different trading characteristics
7. **Realistic execution modeling** — slippage is not constant
8. **Time-of-day filtering** — market behavior varies by session
9. **Volatility spike detection** — indirect news/event detection
10. **Adaptive stops** — stop loss varies by regime
11. **Phased Kelly sizing** — position sizing based on measured performance

---

## 2. Definitions and Conventions

### 2.1 Regime Categories

V7 uses **four primary regime categories**:

| Regime | Description | Trading Implication |
|--------|-------------|---------------------|
| `TREND_UP` | Strong upward directional bias, low noise | Long bias favored |
| `TREND_DOWN` | Strong downward directional bias, low noise | Short bias favored |
| `RANGE` | No clear direction, low volatility | Mean-reversion or NO_TRADE |
| `TRANSITION` | Cannot determine regime / regime change likely | Default to NO_TRADE |

**Note:** `HIGH_VOL_CHAOTIC` is a sub-state of `RANGE` or `TRANSITION`, not a separate primary regime. This simplifies the detector and reduces combinatorial explosion.

### 2.2 Mode-Specific Regime Timeframes

Each trading mode detects regime at its primary timeframe:

| Mode | Primary Timeframe | Context Timeframe | Regime Detected From |
|------|-------------------|-------------------|----------------------|
| `SWING` | 4h | 1d | 4h + 1d candles |
| `SCALP` | 1h | 4h | 1h + 4h candles |
| `AGGRESSIVE_SCALP` | 15m | 1h | 15m + 1h candles |

The **same timestamp** can show different regimes for different modes. This is intentional — aggressive scalp may see chaos where swing sees trend.

### 2.3 Code Conventions

```python
# All regime enums use UPPER_CASE
from enum import Enum

class Regime(Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"


class TradingMode(Enum):
    SWING = "SWING"
    SCALP = "SCALP"
    AGGRESSIVE_SCALP = "AGGRESSIVE_SCALP"
```

---

## 3. Regime Detection Layer

### 3.1 Architecture Position

Regime detection occurs **after** canonical state construction but **before** feature building. This is the first mode-specific processing.

```
canonical_market_state
    ↓
[Regime Detection per Mode]
    ↓
mode_specific_regime_signal
    ↓
feature_builder
    ↓
...
```

### 3.2 Rule-Based Regime Detector

**Principle:** Start with simple rule-based detection, not ML. This is interpretable, debuggable, and stable.

#### 3.2.1 Core Algorithm

```python
"""
Regime Detection Algorithm

Uses ADX for trend strength, ATR percentile for volatility context,
and EMA crossover for direction.

Thresholds are treated as hyperparameters to tune.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import numpy as np


class Regime(Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"


@dataclass(frozen=True)
class RegimeSignal:
    """Immutable output from regime detection."""
    regime: Regime
    confidence: float  # 0.0 to 1.0
    transition_risk: float  # 0.0 to 1.0
    # Raw values for debugging and audit
    adx_value: float
    atr_percentile: float
    trend_slope: float


class RegimeDetector:
    """
    Rule-based regime detector.
    
    Designed for: interpretability, debuggability, stability.
    Can be replaced with ML-based detector in Phase 3.
    """
    
    # THRESHOLD HYPERPARAMETERS - these tune the detector
    ADX_STRONG_TREND = 25.0    # Above this = trend
    ADX_WEAK_TREND = 20.0      # Below this = range/transition
    ATR_LOW_PERCENTILE = 0.25  # Below this = low volatility
    ATR_HIGH_PERCENTILE = 0.75 # Above this = high volatility
    
    # EMA periods for trend direction
    FAST_EMA_PERIOD = 10
    SLOW_EMA_PERIOD = 50
    
    # Lookback for calculations
    LOOKBACK_BARS = 20
    
    def detect(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
    ) -> RegimeSignal:
        """
        Detect regime from price data.
        
        Args:
            closes: Array of close prices (oldest first)
            highs: Array of high prices
            lows: Array of low prices
            
        Returns:
            RegimeSignal with regime classification and confidence
        """
        
        if len(closes) < self.LOOKBACK_BARS:
            # Not enough data - return transition with low confidence
            return RegimeSignal(
                regime=Regime.TRANSITION,
                confidence=0.0,
                transition_risk=1.0,
                adx_value=0.0,
                atr_percentile=0.5,
                trend_slope=0.0
            )
        
        # Calculate indicators
        lookback =closes[-self.LOOKBACK_BARS:]
        lookback_highs = highs[-self.LOOKBACK_BARS:]
        lookback_lows = lows[-self.LOOKBACK_BARS:]
        
        adx = self._calculate_adx(lookback_highs, lookback_lows, lookback)
        atr_percentile = self._calculate_atr_percentile(lookback_highs, lookback_lows, lookback)
        trend_slope = self._calculate_trend_slope(lookback)
        
        # Classify regime
        regime, confidence = self._classify_regime(adx, atr_percentile, trend_slope)
        
        # Calculate transition risk
        transition_risk = self._calculate_transition_risk(
            adx, atr_percentile, closes
        )
        
        return RegimeSignal(
            regime=regime,
            confidence=confidence,
            transition_risk=transition_risk,
            adx_value=adx,
            atr_percentile=atr_percentile,
            trend_slope=trend_slope
        )
    
    def _calculate_adx(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray
    ) -> float:
        """Calculate Average Directional Index (simplified)."""
        
        high_diff = np.diff(highs)
        low_diff = -np.diff(lows)
        
        plus_dm = np.where(
            (high_diff > low_diff) & (high_diff > 0),
            high_diff,
            0
        )
        minus_dm = np.where(
            (low_diff > high_diff) & (low_diff > 0),
            low_diff,
            0
        )
        
        # True Range
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        
        atr = np.mean(tr)
        if atr == 0:
            return 0.0
            
        plus_di = 100 * np.mean(plus_dm) / atr
        minus_di = 100 * np.mean(minus_dm) / atr
        
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        
        return dx
    
    def _calculate_atr_percentile(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray
    ) -> float:
        """Calculate where current ATR sits in recent historical distribution."""
        
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        
        current_atr = np.mean(tr[-5:])
        
        if len(tr) < 10:
            return 0.5
            
        historical_atrs = tr[-self.LOOKBACK_BARS:]
        
        return np.searchsorted(np.sort(historical_atrs), current_atr) / len(historical_atrs)
    
    def _calculate_trend_slope(self, closes: np.ndarray) -> float:
        """Calculate EMA-based trend direction."""
        
        ema_fast = self._ema(closes, self.FAST_EMA_PERIOD)
        ema_slow = self._ema(closes, self.SLOW_EMA_PERIOD)
        
        if len(ema_fast) < 2:
            return 0.0
            
        return (ema_fast[-1] - ema_slow[-1]) / ema_slow[-1]
    
    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average."""
        
        alpha = 2 / (period + 1)
        ema = np.empty(len(data))
        ema[0] = data[0]
        
        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]
        
        return ema
    
    def _classify_regime(
        self,
        adx: float,
        atr_percentile: float,
        trend_slope: float
    ) -> tuple[Regime, float]:
        """Classify into regime based on indicators."""
        
        # Strong trend
        if adx >= self.ADX_STRONG_TREND:
            if trend_slope > 0:
                return Regime.TREND_UP, min(1.0, adx / 35)
            else:
                return Regime.TREND_DOWN, min(1.0, adx / 35)
        
        # Weak trend
        elif adx >= self.ADX_WEAK_TREND:
            if atr_percentile < self.ATR_LOW_PERCENTILE:
                # Low volatility = range
                return Regime.RANGE, 0.7
            elif atr_percentile > self.ATR_HIGH_PERCENTILE:
                # High volatility + weak trend = transition
                return Regime.TRANSITION, 0.6
            else:
                return Regime.RANGE, 0.6
        
        # Very weak ADX = transition or range
        else:
            return Regime.TRANSITION, 0.5
    
    def _calculate_transition_risk(
        self,
        adx: float,
        atr_percentile: float,
        closes: np.ndarray
    ) -> float:
        """Calculate probability that regime is about to change."""
        
        # High volatility spike often precedes transition
        volatility_risk = 0.8 if atr_percentile > 0.85 else (
            0.5 if atr_percentile > 0.7 else 0.2
        )
        
        # Unusual price movements suggest transition
        if len(closes) < 20:
            return 0.5
            
        returns = np.diff(closes) / closes[:-1]
        recent_std = np.std(returns[-10:])
        earlier_std = np.mean(np.std(returns[-20:-10])) + 1e-10
        
        movement_risk = 0.7 if recent_std > earlier_std * 1.5 else 0.3
        
        return (volatility_risk + movement_risk) / 2
```

#### 3.2.2 Configuration

```python
# Config structure for regime detection
from dataclasses import dataclass


@dataclass(frozen=True)
class RegimeDetectorConfig:
    """Configuration for regime detector per trading mode."""
    
    mode: str
    primary_interval: str  # e.g., "4h", "1h", "15m"
    context_interval: str  # e.g., "1d", "4h", "1h"
    lookback_bars: int
    
    # Tunable thresholds (same defaults, can be overridden per mode)
    adx_strong_trend: float = 25.0
    adx_weak_trend: float = 20.0
    atr_low_percentile: float = 0.25
    atr_high_percentile: float = 0.75


# Default configs per mode
REGIME_DETECTOR_CONFIGS = {
    "SWING": RegimeDetectorConfig(
        mode="SWING",
        primary_interval="4h",
        context_interval="1d",
        lookback_bars=20,
    ),
    "SCALP": RegimeDetectorConfig(
        mode="SCALP",
        primary_interval="1h",
        context_interval="4h",
        lookback_bars=30,  # More bars for shorter timeframe
    ),
    "AGGRESSIVE_SCALP": RegimeDetectorConfig(
        mode="AGGRESSIVE_SCALP",
        primary_interval="15m",
        context_interval="1h",
        lookback_bars=40,  # Even more for 15m
    ),
}
```

### 3.3 Mode-Specific Regime Detection Integration

```python
"""
Integration: Detect regime for each trading mode.
"""

from typing import NamedTuple


class MarketState:
    """Canonical market state container."""
    
    def __init__(self, data: dict[str, dict]):
        """
        Args:
            data: Dict keyed by interval, each containing:
                  {"closes": np.ndarray, "highs": np.ndarray, "lows": np.ndarray}
        """
        self._data = data
    
    def get_data(self, interval: str) -> dict:
        """Get data for specific interval."""
        return self._data.get(interval, {"closes": np.array([]), "highs": np.array([]), "lows": np.array([])})


def detect_regimes_for_mode(
    market_state: MarketState,
    mode: str,
    config: RegimeDetectorConfig
) -> RegimeSignal:
    """
    Detect regime for a specific trading mode.
    
    Combines primary and context interval data for detection.
    """
    
    primary = market_state.get_data(config.primary_interval)
    context = market_state.get_data(config.context_interval)
    
    # Combine: context provides historical backdrop
    combined_closes = np.concatenate([context["closes"][-config.lookback_bars:], primary["closes"]])
    combined_highs = np.concatenate([context["highs"][-config.lookback_bars:], primary["highs"]])
    combined_lows = np.concatenate([context["lows"][-config.lookback_bars:], primary["lows"]])
    
    # Use only the most recent bars for detection
    lookback = combined_closes[-config.lookback_bars:]
    lookback_highs = combined_highs[-config.lookback_bars:]
    lookback_lows = combined_lows[-config.lookback_bars:]
    
    detector = RegimeDetector()
    
    return detector.detect(lookback, lookback_highs, lookback_lows)


def detect_all_mode_regimes(
    market_state: MarketState
) -> dict[str, RegimeSignal]:
    """
    Detect regime for all trading modes.
    
    Returns:
        Dict mapping mode -> RegimeSignal
    """
    
    results = {}
    
    for mode, config in REGIME_DETECTOR_CONFIGS.items():
        results[mode] = detect_regimes_for_mode(market_state, mode, config)
    
    return results
```

---

## 4. Enhanced Labels with Regime Context

### 4.1 Label Schema Extension

Labels must include regime context. This allows the model to learn conditional behavior.

```python
"""
Extended label schema for regime-aware training.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Regime(Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"


@dataclass(frozen=True)
class ExtendedLabelSet:
    """
    Complete label set including regime context.
    
    This replaces the base LabelSet from pipeline/labels.md
    """
    
    # === Core Labels (from base design) ===
    best_action_label: str  # LONG_NOW | SHORT_NOW | NO_TRADE
    second_best_action_label: str
    
    # Classification targets
    long_success_label: int  # 0/1
    short_success_label: int  # 0/1
    no_trade_quality_label: int  # 0/1
    skip_was_correct: bool
    
    # Regression targets
    long_realized_r_net: float
    short_realized_r_net: float
    long_mae_r: float
    short_mae_r: float
    long_mfe_r: float
    short_mfe_r: float
    regret_r: float
    saved_loss_score: float
    missed_opportunity_score: float
    
    # === NEW: Regime Context ===
    regime_at_decision: Regime
    regime_confidence: float
    regime_transition_risk: float
    
    # === NEW: Aggressive Scalp Specific (only for that mode) ===
    liquidity_quality: Optional[str] = None  # HIGH | LOW
    spread_state: Optional[str] = None       # NORMAL | WIDE
    
    # === Metadata ===
    label_validity: str  # VALID | AMBIGUOUS | UNRESOLVED | INVALID
    ambiguity_reason: Optional[str] = None


def build_extended_labels(
    mode: str,
    regime_signal: RegimeSignal,
    simulation_outputs: dict,
    config: dict
) -> ExtendedLabelSet:
    """
    Build extended label set with regime context.
    
    Args:
        mode: Trading mode (SWING, SCALP, AGGRESSIVE_SCALP)
        regime_signal: Output from regime detector
        simulation_outputs: Output from simulation truth layer
        config: Label configuration
        
    Returns:
        Extended label set with all required fields
    """
    
    # Extract base labels from simulation
    base_labels = _extract_base_labels(simulation_outputs, config)
    
    # Add regime context
    regime_context = {
        "regime_at_decision": regime_signal.regime,
        "regime_confidence": regime_signal.confidence,
        "regime_transition_risk": regime_signal.transition_risk,
    }
    
    # Add aggressive scalp specific if applicable
    scalp_specific = {}
    if mode == "AGGRESSIVE_SCALP":
        scalp_specific = {
            "liquidity_quality": _estimate_liquidity_quality(simulation_outputs),
            "spread_state": _estimate_spread_state(simulation_outputs),
        }
    
    return ExtendedLabelSet(
        **base_labels,
        **regime_context,
        **scalp_specific,
    )


def _estimate_liquidity_quality(simulation_outputs: dict) -> str:
    """Estimate liquidity quality from execution assumptions."""
    # This would use historical volume data
    # Simplified for now
    return "HIGH"  # Placeholder


def _estimate_spread_state(simulation_outputs: dict) -> str:
    """Estimate spread state from volatility."""
    # This would use actual spread data if available
    return "NORMAL"  # Placeholder
```

### 4.2 Label Production Pipeline

```python
"""
Label production with regime awareness.
"""

def produce_labels(
    market_state: MarketState,
    symbol: str,
    timestamp: int,
    mode: str,
    simulation_config: dict
) -> ExtendedLabelSet:
    """
    Produce labels for a single decision point.
    
    Flow:
    1. Detect regime for this mode
    2. Run simulation with mode-specific config
    3. Build extended labels with regime context
    """
    
    # Step 1: Detect regime
    regime_config = REGIME_DETECTOR_CONFIGS[mode]
    regime_signal = detect_regimes_for_mode(market_state, mode, regime_config)
    
    # Step 2: Run simulation (with regime-aware config)
    sim_outputs = run_simulation(
        market_state=market_state,
        symbol=symbol,
        timestamp=timestamp,
        config=_get_regime_aware_sim_config(mode, regime_signal, simulation_config)
    )
    
    # Step 3: Build labels
    label_config = get_label_config(mode)
    labels = build_extended_labels(mode, regime_signal, sim_outputs, label_config)
    
    return labels


def _get_regime_aware_sim_config(
    mode: str,
    regime_signal: RegimeSignal,
    base_config: dict
) -> dict:
    """
    Adjust simulation config based on regime.
    
    Different regimes may need different stop/target parameters.
    """
    
    config = base_config.copy()
    
    # In transition regime, use wider stops
    if regime_signal.regime == Regime.TRANSITION:
        config["stop_multiplier"] = base_config.get("stop_multiplier", 2.0) * 1.5
        config["target_multiplier"] = base_config.get("target_multiplier", 2.0) * 1.3
    
    # In high volatility, increase stop to avoid gapouts
    if regime_signal.atr_percentile > 0.8:
        config["stop_multiplier"] = config.get("stop_multiplier", 2.0) * 1.3
    
    return config
```

---

## 5. Feature Extension for Regime

### 5.1 Regime as Feature vs Regime as Router

**Decision:** Regime is NOT simply added as a feature. Instead:

1. Regime is detected first
2. Regime is encoded as **categorical features** for the model
3. Policy uses regime for **threshold modification**
4. Evaluation tests performance **by regime**

```python
"""
Feature extension to include regime context.
"""

def build_features_with_regime(
    market_state: MarketState,
    mode: str,
    regime_signal: RegimeSignal,
    feature_config: dict
) -> dict:
    """
    Build feature vector including regime context.
    """
    
    # Get base features from pipeline/features.md
    base_features = build_base_features(market_state, mode, feature_config)
    
    # Add regime features
    regime_features = {
        # One-hot encoded regime
        f"regime_is_trend_up": 1.0 if regime_signal.regime == Regime.TREND_UP else 0.0,
        f"regime_is_trend_down": 1.0 if regime_signal.regime == Regime.TREND_DOWN else 0.0,
        f"regime_is_range": 1.0 if regime_signal.regime == Regime.RANGE else 0.0,
        f"regime_is_transition": 1.0 if regime_signal.regime == Regime.TRANSITION else 0.0,
        
        # Regime confidence
        "regime_confidence": regime_signal.confidence,
        
        # Transition risk
        "regime_transition_risk": regime_signal.transition_risk,
        
        # Raw regime detector output for debugging
        "regime_adx": regime_signal.adx_value,
        "regime_atr_percentile": regime_signal.atr_percentile,
        "regime_trend_slope": regime_signal.trend_slope,
    }
    
    # Merge
    return {**base_features, **regime_features}
```

---

## 6. Policy Extension for Regime

### 6.1 Regime-Aware Threshold Modification

Policy thresholds must vary by regime. The model outputs remain the same, but the decision gates change.

```python
"""
Policy extension for regime-aware decision making.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Action(Enum):
    LONG_NOW = "LONG_NOW"
    SHORT_NOW = "SHORT_NOW"
    NO_TRADE = "NO_TRADE"


@dataclass
class PolicyThresholds:
    """Policy thresholds that vary by regime."""
    
    # Base thresholds (from pipeline/policy.md)
    min_confidence: float
    min_expected_r: float
    min_cost_adjusted_expectancy: float
    max_expected_drawdown: float
    
    # Regime modification factors
    confidence_multiplier: float = 1.0
    expected_r_multiplier: float = 1.0
    
    # Special regime actions
    allow_long: bool = True
    allow_short: bool = True
    require_no_trade: bool = False


REGIME_THRESHOLDS = {
    # In strong trends, prefer the trend direction
    Regime.TREND_UP: PolicyThresholds(
        min_confidence=0.6,
        min_expected_r=1.2,
        min_cost_adjusted_expectancy=0.8,
        max_expected_drawdown=1.5,
        confidence_multiplier=0.9,  # Slightly lower threshold
        expected_r_multiplier=0.9,
        allow_long=True,
        allow_short=False,  # Don't fight the trend
        require_no_trade=False,
    ),
    Regime.TREND_DOWN: PolicyThresholds(
        min_confidence=0.6,
        min_expected_r=1.2,
        min_cost_adjusted_expectancy=0.8,
        max_expected_drawdown=1.5,
        confidence_multiplier=0.9,
        expected_r_multiplier=0.9,
        allow_long=False,  # Don't fight the trend
        allow_short=True,
        require_no_trade=False,
    ),
    # In range, stricter thresholds, prefer no-trade
    Regime.RANGE: PolicyThresholds(
        min_confidence=0.7,
        min_expected_r=1.5,
        min_cost_adjusted_expectancy=1.0,
        max_expected_drawdown=1.0,
        confidence_multiplier=1.1,  # Higher threshold
        expected_r_multiplier=1.2,
        allow_long=True,
        allow_short=True,
        require_no_trade=False,
    ),
    # In transition, default to no-trade
    Regime.TRANSITION: PolicyThresholds(
        min_confidence=0.8,
        min_expected_r=2.0,
        min_cost_adjusted_expectancy=1.5,
        max_expected_drawdown=0.8,
        confidence_multiplier=1.3,  # Much higher
        expected_r_multiplier=1.5,
        allow_long=True,
        allow_short=True,
        require_no_trade=False,  # Let model decide but with very high bars
    ),
}


def apply_regime_to_policy(
    base_thresholds: PolicyThresholds,
    regime_signal: RegimeSignal
) -> PolicyThresholds:
    """
    Apply regime modification to base policy thresholds.
    """
    
    regime_thresholds = REGIME_THRESHOLDS[regime_signal.regime]
    
    # Apply multipliers
    adjusted = PolicyThresholds(
        min_confidence=base_thresholds.min_confidence * regime_thresholds.confidence_multiplier,
        min_expected_r=base_thresholds.min_expected_r * regime_thresholds.expected_r_multiplier,
        min_cost_adjusted_expectancy=base_thresholds.min_cost_adjusted_expectancy * regime_thresholds.expected_r_multiplier,
        max_expected_drawdown=base_thresholds.max_expected_drawdown,
        confidence_multiplier=regime_thresholds.confidence_multiplier,
        expected_r_multiplier=regime_thresholds.expected_r_multiplier,
        allow_long=regime_thresholds.allow_long,
        allow_short=regime_thresholds.allow_short,
        require_no_trade=regime_thresholds.require_no_trade,
    )
    
    # Override directional restrictions
    if not regime_thresholds.allow_long:
        adjusted.min_expected_r = 999  # Effectively block long
    if not regime_thresholds.allow_short:
        adjusted.min_expected_r = 999  # Effectively block short
    
    # If transition risk is high, further increase no-trade tendency
    if regime_signal.transition_risk > 0.7:
        adjusted.min_expected_r *= 1.3
        adjusted.min_confidence *= 1.1
    
    return adjusted
```

---

## 7. Evaluation Extension for Regime

### 7.1 Regime-Aware Walk-Forward

Evaluation must test not just time-based performance but **regime-based** performance.

```python
"""
Evaluation extension for regime-aware testing.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class RegimeAwareMetrics:
    """Metrics broken down by regime."""
    
    # Overall metrics
    overall_expectancy_r: float
    overall_win_rate: float
    overall_max_drawdown: float
    
    # Per-regime metrics
    trend_up_metrics: Optional[dict] = None
    trend_down_metrics: Optional[dict] = None
    range_metrics: Optional[dict] = None
    transition_metrics: Optional[dict] = None
    
    # Cross-regime metrics (critical for production)
    same_regime_holdout_performance: float = 0.0
    regime_transition_performance: float = 0.0
    out_of_sample_regime_performance: float = 0.0


def evaluate_with_regime_breakdown(
    model_outputs: list[dict],
    actual_outcomes: list[dict],
    regime_labels: list[Regime]
) -> RegimeAwareMetrics:
    """
    Evaluate model performance with regime breakdown.
    
    Key insight: Performance in same regime during training vs 
    performance in regime transition is what matters in production.
    """
    
    metrics = RegimeAwareMetrics(
        overall_expectancy_r=_calculate_expectancy(actual_outcomes),
        overall_win_rate=_calculate_win_rate(actual_outcomes),
        overall_max_drawdown=_calculate_max_drawdown(actual_outcomes),
    )
    
    # Per-regime breakdown
    regime_groups = _group_by_regime(model_outputs, actual_outcomes, regime_labels)
    
    for regime_name, (outputs, outcomes) in regime_groups.items():
        setattr(metrics, f"{regime_name}_metrics", {
            "expectancy_r": _calculate_expectancy(outcomes),
            "win_rate": _calculate_win_rate(outcomes),
            "sample_count": len(outcomes),
        })
    
    # Regime transition performance
    # This is critical: how does the model perform when regime changes?
    metrics.regime_transition_performance = _calculate_transition_performance(
        model_outputs, actual_outcomes, regime_labels
    )
    
    # Out-of-regime performance (did model see this regime in training?)
    metrics.out_of_sample_regime_performance = _calculate_unseen_regime_performance(
        model_outputs, actual_outcomes, regime_labels
    )
    
    return metrics


def _calculate_transition_performance(
    outputs: list[dict],
    outcomes: list[dict],
    regimes: list[Regime]
) -> float:
    """Calculate performance during regime transitions."""
    
    if len(regimes) < 2:
        return 0.0
    
    transition_outcomes = []
    
    for i in range(1, len(regimes)):
        if regimes[i] != regimes[i-1]:
            # This is a regime transition point
            transition_outcomes.append(outcomes[i])
    
    if not transition_outcomes:
        return 0.0
        
    return _calculate_expectancy(transition_outcomes)


def _calculate_unseen_regime_performance(
    outputs: list[dict],
    outcomes: list[dict],
    regimes: list[Regime]
) -> float:
    """
    Calculate performance on regimes not seen during training.
    
    In production, model will encounter new regimes.
    This metric shows graceful degradation.
    """
    # Simplified - in practice would need train/eval split by regime
    return _calculate_expectancy(outcomes)  # Placeholder
```

### 7.2 Promotion Gate Addition

```python
"""
Extended promotion criteria to include regime requirements.
"""

@dataclass
class ExtendedPromotionCriteria:
    """Extended promotion criteria including regime performance."""
    
    # Base criteria (from pipeline/evaluation.md)
    min_expectancy_r: float = 1.0
    min_win_rate: float = 0.40
    min_no_trade_quality: float = 0.5
    min_calibration_quality: float = 0.6
    
    # NEW: Regime-specific criteria
    min_same_regime_performance: float = 0.9
    min_regime_transition_performance: float = 0.7  # Can be lower due to uncertainty
    max_out_of_regime_degradation: float = 0.4  # Max performance drop in unseen regime


def evaluate_promotion_eligibility(
    metrics: RegimeAwareMetrics,
    criteria: ExtendedPromotionCriteria
) -> tuple[bool, list[str]]:
    """
    Evaluate whether model is eligible for promotion.
    
    Returns:
        (is_eligible, list of reasons for denial)
    """
    
    reasons = []
    
    # Base criteria checks
    if metrics.overall_expectancy_r < criteria.min_expectancy_r:
        reasons.append(f"Expectancy R {metrics.overall_expectancy_r:.2f} below threshold {criteria.min_expectancy_r}")
    
    # Regime criteria checks
    if metrics.same_regime_holdout_performance < criteria.min_same_regime_performance:
        reasons.append(f"Same-regime performance {metrics.same_regime_holdout_performance:.2f} below threshold")
    
    if metrics.regime_transition_performance < criteria.min_regime_transition_performance:
        reasons.append(f"Regime transition performance {metrics.regime_transition_performance:.2f} below threshold")
    
    return len(reasons) == 0, reasons
```

---

## 8. Symbol-Specific Parameters

### 8.1 Symbol Profile Database

Different symbols have fundamentally different trading characteristics.

```python
"""
Symbol-specific parameters for trading decisions.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class LiquidityTier(Enum):
    ULTRA_HIGH = "ultra_high"  # BTC, ETH
    VERY_HIGH = "very_high"    # Top 10 alts
    HIGH = "high"              # Top 50 alts
    MEDIUM = "medium"          # Top 100 alts
    LOW = "low"                # Small caps
    VERY_LOW = "very_low"      # Micro caps


class VolatilityProfile(Enum):
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


@dataclass(frozen=True)
class SymbolProfile:
    """Trading characteristics for a specific symbol."""
    
    symbol: str
    maker_fee_pct: float
    min_order_size: float
    avg_daily_volume_usd: float
    liquidity_tier: LiquidityTier
    volatility_profile: VolatilityProfile
    typical_spread_pct: float
    correlation_to_btc: float
    official_name: str


# Pre-configured symbol profiles
# In production, this would be loaded from database and updated periodically
SYMBOL_PROFILES = {
    "BTCUSDT": SymbolProfile(
        symbol="BTCUSDT",
        maker_fee_pct=0.02,
        min_order_size=0.0001,
        avg_daily_volume_usd=5_000_000_000,
        liquidity_tier=LiquidityTier.ULTRA_HIGH,
        volatility_profile=VolatilityProfile.MEDIUM,
        typical_spread_pct=0.001,
        correlation_to_btc=1.0,
        official_name="Bitcoin",
    ),
    "ETHUSDT": SymbolProfile(
        symbol="ETHUSDT",
        maker_fee_pct=0.02,
        min_order_size=0.001,
        avg_daily_volume_usd=2_000_000_000,
        liquidity_tier=LiquidityTier.VERY_HIGH,
        volatility_profile=VolatilityProfile.MEDIUM,
        typical_spread_pct=0.001,
        correlation_to_btc=0.85,
        official_name="Ethereum",
    ),
    "BNBUSDT": SymbolProfile(
        symbol