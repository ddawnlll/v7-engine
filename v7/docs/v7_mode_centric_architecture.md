# V7 Mode-Centric Architecture - Complete Change Specification

**Status:** Master Design Document  
**Version:** 1.0  
**Purpose:** Define complete architectural changes from single-pipeline to mode-centric system

---

## 1. Executive Summary

### 1.1 The Problem

Current V7 claims to support 3 trading modes (SWING, SCALP, AGGRESSIVE_SCALP) but operates as a single unified system with:
- One simulation config
- One label family
- One model artifact
- One policy threshold set
- Hardcoded 4h primary timeframe

This causes **regime agnosticism** — the same pattern produces the same prediction regardless of market conditions. Real-market viability: **5.5/10**.

### 1.2 The Solution

A **mode-centric architecture** where each mode operates as an independent pipeline with its own:
- Simulation configuration
- Label production
- Model artifact
- Policy thresholds
- Regime detection engine

Additionally, **regime-aware decisions** modify behavior based on detected market regime.

### 1.3 Target Score

With full implementation: **7.5-8.5/10** (realistic ceiling based on diminishing returns)

---

## 2. Core Architecture Changes

### 2.1 Before vs After

```
BEFORE (Current V7):
━━━━━━━━━━━━━━━━━━━━
Market Data → Single Pipeline → Single Output
                ↓
         [4h primary]
         [single sim config]
         [single label set]
         [single model]
         [single policy]

AFTER (V7 Mode-Centric):
━━━━━━━━━━━━━━━━━━━━━━━━━
Market Data → Mode Router → 3 Independent Pipelines
                    ↓
              ┌─────┴─────┐
              ↓           ↓
         SWING        SCALP         AGGRESSIVE_SCALP
         mode         mode          mode
              ↓           ↓           ↓
         [4h + 1d]    [1h + 4h]     [15m + 1h]
         sim_config   sim_config    sim_config
         labels       labels        labels
         model        model         model
         policy       policy        policy
         regime       regime        regime
```

### 2.2 Dataset Structure Change

**Critical:** The same timestamp produces **3 different label truths**:

```python
# Example:
# BTCUSDT | 2024-01-15 14:00 | SWING            → best_action = LONG
# BTCUSDT | 2024-01-15 14:00 | SCALP            → best_action = NO_TRADE
# BTCUSDT | 2024-01-15 14:00 | AGGRESSIVE_SCALP → best_action = SHORT
```

Dataset row now includes:
```python
{
    "symbol": "BTCUSDT",
    "timestamp": 1705327200,
    "mode": "SWING",  # or "SCALP" or "AGGRESSIVE_SCALP"
    "primary_interval": "4h",
    "features": [...],
    "labels": {...},  # mode-specific
}
```

**Feature sharing:** Features are shared across modes (built from canonical state). **Labels are mode-specific.**

---

## 3. Mode-Specific Simulation Configuration

### 3.1 Configuration Table

| Parameter | SWING | SCALP | AGGRESSIVE_SCALP |
|-----------|-------|-------|------------------|
| Primary interval | 4h | 30m/1h | 15m |
| Context interval | 1d | 4h | 1h |
| Refinement interval | 1h | 15m | 5m |
| Max holding bars | 12-30 | 3-12 | 1-5 |
| Stop multiplier (ATR) | 2.0-2.5 | 1.5-2.0 | 1.0-1.5 |
| Target multiplier (ATR) | 2.0-3.0 | 1.5-2.0 | 1.0-1.5 |
| Ambiguity margin (R) | 0.20 | 0.10 | 0.05 |
| Min action edge (R) | 0.35 | 0.15 | 0.08 |
| MAE penalty weight | MEDIUM | HIGH | VERY_HIGH |
| Cost penalty weight | MEDIUM | HIGH | VERY_HIGH |
| NO_TRADE tendency | LOW | MEDIUM | HIGH (default) |

### 3.2 YAML Config Structure

```yaml
simulation_configs:
  swing:
    primary_interval: "4h"
    context_intervals: ["1d", "1h"]
    max_holding_bars: 30
    stop_method: "atr_wide"
    target_method: "atr_wide"
    ambiguity_margin_r: 0.20
    min_action_edge_r: 0.35
    mae_penalty_weight: "medium"
    cost_penalty_weight: "medium"
    # Labels:
    # - success if long_realized_r_net >= 0.75R
    # - success if mae >= -0.60R

  scalp:
    primary_interval: "1h"
    context_intervals: ["4h", "15m"]
    max_holding_bars: 12
    stop_method: "atr_medium"
    target_method: "atr_medium"
    ambiguity_margin_r: 0.10
    min_action_edge_r: 0.15
    mae_penalty_weight: "high"
    cost_penalty_weight: "very_high"
    # Labels:
    # - success if long_realized_r_net >= 0.20R
    # - success if mae >= -0.25R
    # - requires cost_adjusted_expectancy > 0

  aggressive_scalp:
    primary_interval: "15m"
    context_intervals: ["1h", "5m"]
    max_holding_bars: 5
    stop_method: "atr_tight"
    target_method: "atr_tight"
    ambiguity_margin_r: 0.05
    min_action_edge_r: 0.08
    mae_penalty_weight: "very_high"
    cost_penalty_weight: "very_high"
    no_trade_default: true
    # Labels:
    # - success if long_realized_r_net >= 0.10R
    # - success if mae >= -0.10R
    # - time_to_mfe_bars <= 3 is required
```

---

## 4. Mode-Specific Label Design

### 4.1 Label Categories

Each mode produces its own label set:

```python
@dataclass
class ModeLabels:
    """
    Extended label set for mode-centric training.
    """
    # === Classification Targets ===
    best_action_label: str          # LONG_NOW | SHORT_NOW | NO_TRADE
    second_best_action_label: str
    long_success_label: int          # Binary (0/1)
    short_success_label: int         # Binary (0/1)
    no_trade_quality_label: int      # 0=bad_skip, 1=good_skip
    skip_was_correct: bool
    
    # === Regression Targets ===
    long_realized_r_net: float       # Net R after costs
    short_realized_r_net: float
    long_mae_r: float                # Maximum adverse excursion
    short_mae_r: float
    long_mfe_r: float                # Maximum favorable excursion
    short_mfe_r: float
    long_cost_r: float
    short_cost_r: float
    
    # === Advanced (mode-specific) ===
    regret_r: float                  # Opportunity cost of wrong choice
    saved_loss_score: float          # How much loss was avoided
    missed_opportunity_score: float  # How much gain was missed
    
    # === Mode-specific additions ===
    # For SCALP and AGGRESSIVE_SCALP:
    long_time_to_mfe_bars: Optional[int] = None
    short_time_to_mfe_bars: Optional[int] = None
    long_exit_efficiency: Optional[float] = None
    short_exit_efficiency: Optional[float] = None
    
    # For AGGRESSIVE_SCALP only:
    instant_adverse_label: Optional[int] = None  # Immediate drawdown flag
    
    # === Metadata ===
    label_validity: str              # VALID | AMBIGUOUS | UNRESOLVED
    ambiguity_reason: Optional[str] = None
    action_margin_r: float = 0.0     # Gap between best and second-best
```

### 4.2 Mode-Specific Success Thresholds

```python
SUCCESS_THRESHOLDS = {
    "SWING": {
        "min_net_r_for_success": 0.75,
        "max_mae_r_for_success": -0.60,
        "min_mfe_r_for_good_exit": 1.0,
        "allow_no_trade_on_ambiguity": False,
    },
    "SCALP": {
        "min_net_r_for_success": 0.20,
        "max_mae_r_for_success": -0.25,
        "min_cost_adjusted_expectancy": 0.10,  # REQUIRED
        "allow_no_trade_on_ambiguity": True,
    },
    "AGGRESSIVE_SCALP": {
        "min_net_r_for_success": 0.10,
        "max_mae_r_for_success": -0.10,
        "max_time_to_mfe_bars": 3,
        "instant_adverse_threshold": -0.05,  # Immediate loss flag
        "no_trade_default": True,
    },
}
```

### 4.3 Utility Function for Best Action

```python
def calculate_action_utility(action: str, labels: ModeLabels, mode: str) -> float:
    """
    Calculate utility score for best action selection.
    Different modes weight factors differently.
    """
    
    # Mode-specific weights
    weights = {
        "SWING": {"mae": 1.0, "cost": 1.0, "time": 0.3},
        "SCALP": {"mae": 2.0, "cost": 2.0, "time": 1.5},
        "AGGRESSIVE_SCALP": {"mae": 3.0, "cost": 3.0, "time": 2.5},
    }
    
    w = weights[mode]
    
    if action == "LONG_NOW":
        return (
            labels.long_realized_r_net
            - w["mae"] * abs(labels.long_mae_r)
            - w["cost"] * labels.long_cost_r
            - w["time"] * labels.long_time_to_mfe_bars * 0.1
        )
    elif action == "SHORT_NOW":
        return (
            labels.short_realized_r_net
            - w["mae"] * abs(labels.short_mae_r)
            - w["cost"] * labels.short_cost_r
            - w["time"] * labels.short_time_to_mfe_bars * 0.1
        )
    else:  # NO_TRADE
        return labels.saved_loss_score
```

---

## 5. Regime-Aware System

### 5.1 Regime Categories (Unified Across Modes)

| Regime | Description | Trading Action |
|--------|-------------|----------------|
| `TREND_UP` | Strong upward directional bias, ADX > 25 | Favor LONG, avoid SHORT |
| `TREND_DOWN` | Strong downward directional bias, ADX > 25 | Favor SHORT, avoid LONG |
| `RANGE` | No clear direction, low-to-medium volatility | Conservative, prefer NO_TRADE |
| `TRANSITION` | High volatility, regime unclear | Default to NO_TRADE |

**Note:** `HIGH_VOL_CHAOTIC` is a sub-state of RANGE or TRANSITION, NOT a separate regime.

### 5.2 Mode-Specific Regime Detection

Each mode detects regime at its own timeframe:

```python
REGIME_DETECTION_CONFIGS = {
    "SWING": {
        "primary_bars": "4h",
        "context_bars": "1d",
        "indicators": ["adx", "atr_percentile", "ema_slope", "structure_count"],
    },
    "SCALP": {
        "primary_bars": "1h",
        "context_bars": "4h",
        "indicators": ["atr_expansion", "ema_separation", "buying_pressure"],
    },
    "AGGRESSIVE_SCALP": {
        "primary_bars": "15m",
        "context_bars": "1h",
        "indicators": ["body_ratio", "micro_momentum", "spread_proxy", "atr_percentile"],
    },
}
```

### 5.3 Regime Detection Algorithm (Rule-Based)

```python
from dataclasses import dataclass
from enum import Enum
import numpy as np


class Regime(Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"


@dataclass
class RegimeSignal:
    """Output from regime detection."""
    regime: Regime
    confidence: float           # 0.0-1.0
    transition_risk: float     # 0.0-1.0
    adx_value: float
    atr_percentile: float
    trend_slope: float


class RegimeDetector:
    """Rule-based regime detector."""

    # Threshold hyperparameters (tune these)
    ADX_STRONG = 25.0
    ADX_WEAK = 20.0
    ATR_LOW = 0.25
    ATR_HIGH = 0.75

    def detect(self, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> RegimeSignal:
        """Detect regime from price data."""
        
        if len(closes) < 20:
            return RegimeSignal(Regime.TRANSITION, 0.0, 1.0, 0.0, 0.5, 0.0)
        
        # Calculate indicators
        adx = self._calc_adx(highs, lows, closes)
        atr_pctl = self._calc_atr_percentile(highs, lows, closes)
        trend_slope = self._calc_trend_slope(closes)
        
        # Classify
        if adx >= self.ADX_STRONG:
            if trend_slope > 0:
                regime = Regime.TREND_UP
            else:
                regime = Regime.TREND_DOWN
            confidence = min(1.0, adx / 35)
        elif adx >= self.ADX_WEAK:
            if atr_pctl < self.ATR_LOW:
                regime = Regime.RANGE
                confidence = 0.7
            elif atr_pctl > self.ATR_HIGH:
                regime = Regime.TRANSITION
                confidence = 0.6
            else:
                regime = Regime.RANGE
                confidence = 0.6
        else:
            regime = Regime.TRANSITION
            confidence = 0.5
        
        # Transition risk
        trans_risk = self._calc_transition_risk(adx, atr_pctl, closes)
        
        return RegimeSignal(regime, confidence, trans_risk, adx, atr_pctl, trend_slope)

    def _calc_adx(self, highs, lows, closes) -> float:
        """Calculate ADX (simplified)."""
        # Implementation: compute +DI, -DI, then DX
        # Returns: ADX value
        pass  # Full implementation in v7_regime_aware_extensions.md

    def _calc_atr_percentile(self, highs, lows, closes) -> float:
        """Current ATR as percentile of recent history."""
        pass  # Full implementation in v7_regime_aware_extensions.md

    def _calc_trend_slope(self, closes) -> float:
        """EMA(10) - EMA(50) / price."""
        pass

    def _calc_transition_risk(self, adx, atr_pctl, closes) -> float:
        """High volatility = likely regime change."""
        vol_risk = 0.8 if atr_pctl > 0.85 else (0.5 if atr_pctl > 0.7 else 0.2)
        
        if len(closes) < 20:
            return 0.5
        returns = np.diff(closes) / closes[:-1]
        recent_std = np.std(returns[-10:])
        earlier_std = np.mean(np.std(returns[-20:-10])) + 1e-10
        move_risk = 0.7 if recent_std > earlier_std * 1.5 else 0.3
        
        return (vol_risk + move_risk) / 2
```

### 5.4 Regime-Aware Policy Modifiers

```python
REGIME_POLICY_MODIFIERS = {
    Regime.TREND_UP: {
        "confidence_mult": 0.9,
        "expected_r_mult": 0.9,
        "allow_long": True,
        "allow_short": False,  # Don't fight the trend
    },
    Regime.TREND_DOWN: {
        "confidence_mult": 0.9,
        "expected_r_mult": 0.9,
        "allow_long": False,
        "allow_short": True,
    },
    Regime.RANGE: {
        "confidence_mult": 1.1,
        "expected_r_mult": 1.2,
        "allow_long": True,
        "allow_short": True,
    },
    Regime.TRANSITION: {
        "confidence_mult": 1.3,
        "expected_r_mult": 1.5,
        "allow_long": True,
        "allow_short": True,
        "require_no_trade": True,  # Very high barrier
    },
}


def apply_regime_to_policy(base_thresholds: dict, regime: RegimeSignal) -> dict:
    """Apply regime modifications to policy thresholds."""
    
    mod = REGIME_POLICY_MODIFIERS[regime.regime]
    
    return {
        "min_confidence": base_thresholds["min_confidence"] * mod["confidence_mult"],
        "min_expected_r": base_thresholds["min_expected_r"] * mod["expected_r_mult"],
        "allow_long": mod["allow_long"],
        "allow_short"] = mod["allow_short"],
    }
```

### 5.5 Labels with Regime Context

```python
def build_extended_labels(mode, regime_signal, simulation_outputs, config):
    """Build labels including regime context."""
    
    base_labels = _extract_base_labels(simulation_outputs)
    
    return {
        **base_labels,
        # Regime context
        "regime": regime_signal.regime.value,
        "regime_confidence": regime_signal.confidence,
        "regime_transition_risk": regime_signal.transition_risk,
    }
```

---

## 6. Execution Reality Extensions

### 6.1 Symbol-Specific Parameters

```python
SYMBOL_PROFILES = {
    "BTCUSDT": {
        "maker_fee_pct": 0.02,
        "base_slippage": 0.0002,
        "liquidity_tier": "ultra_high",
        "volatility_profile": "medium",
        "min_edge_multiplier": 1.0,
        "avg_daily_volume_usd": 5_000_000_000,
    },
    "ETHUSDT": {
        "maker_fee_pct": 0.02,
        "base_slippage": 0.0003,
        "liquidity_tier": "very_high",
        "volatility_profile": "medium",
        "min_edge_multiplier": 1.1,
        "avg_daily_volume_usd": 2_000_000_000,
    },
    # Small cap altcoin
    "XXXUSDT": {
        "maker_fee_pct": 0.10,
        "base_slippage": 0.002,
        "liquidity_tier": "low",
        "volatility_profile": "very_high",
        "min_edge_multiplier": 3.0,  # 3x more edge required
        "avg_daily_volume_usd": 50_000,
    },
}
```

### 6.2 Dynamic Slippage Model

```python
def estimate_slippage(symbol, position_size, regime, volume_regime):
    """Estimate realistic slippage for a trade."""
    
    profile = SYMBOL_PROFILES[symbol]
    base = profile["base_slippage"]
    
    # Size impact
    vol_ratio = position_size / profile["avg_daily_volume_usd"]
    size_impact = vol_ratio * 0.01
    
    # Regime multipliers
    regime_mult = {
        "TREND_UP": 1.0,
        "TREND_DOWN": 1.0,
        "RANGE": 1.2,
        "TRANSITION": 3.0,
    }
    
    # Volume regime (from section 6.3)
    vol_mult = {
        "HIGH_LIQUIDITY": 0.8,
        "NORMAL_LIQUIDITY": 1.0,
        "LOW_LIQUIDITY": 2.5,
    }
    
    return base + size_impact * regime_mult[regime] * vol_mult[volume_regime]
```

### 6.3 Volume-Based Liquidity Filtering

```python
def get_volume_regime(bars, symbol):
    """
    Determine liquidity regime from actual volume data.
    NOT session-based (Binance is 24/7).
    """
    
    current_vol = bars[-1].volume
    baseline_vol = np.mean([b.volume for b in bars[-168:]])  # 1 week
    
    ratio = current_vol / baseline_vol
    
    if ratio > 1.5:
        return "HIGH_LIQUIDITY"   # Temiz hareket, düşük slippage
    elif ratio < 0.5:
        return "LOW_LIQUIDITY"    # Gürültülü, yüksek slippage
    else:
        return "NORMAL_LIQUIDITY"


def apply_liquidity_filter(action, volume_regime, symbol_profile):
    """Apply liquidity-based filtering to actions."""
    
    if volume_regime == "LOW_LIQUIDITY":
        # Require much higher edge for small caps
        required_mult = symbol_profile.get("min_edge_multiplier", 1.0) * 1.5
        # Could override action to NO_TRADE if edge insufficient
        return action if action.confidence > 0.8 else "NO_TRADE"
    
    return action
```

### 6.4 Volatility Spike Detection (Indirect News Detector)

```python
def is_volatility_spike(bars, threshold=2.5):
    """
    Detect unusual volatility spike.
    Used as proxy for news events.
    
    Returns: True if likely news/recent event -> default to NO_TRADE
    """
    
    current_atr = compute_atr(bars[-5:])
    baseline_atr = compute_atr(bars[-50:-5])
    
    if current_atr > baseline_atr * threshold:
        return True
    
    return False


# Usage in policy:
def decide_from_model(model_output, bars):
    if is_volatility_spike(bars):
        return "NO_TRADE"  # Override model decision
    
    return model_output["recommended_action"]
```

---

## 6.5 Kelly Position Sizing (Phase 2)

### 6.5.1 The Problem

Fixed position sizing ignores edge quality. Kelly Criterion optimizes size based on win rate and edge.

**Warning:** Do NOT use Kelly without real live data. Measure win rate and expected R first.

### 6.5.2 Phased Implementation

```python
class KellyPositionSizer:
    """
    Phased Kelly position sizing.
    
    Phase 1 (first 3 months): Track only, no execution
    Phase 2 (3-6 months): Eighth-Kelly (kelly * 0.125)
    Phase 3 (6+ months): Quarter-Kelly (kelly * 0.25) if stable
    """
    
    def __init__(self, phase="track_only", max_position_pct=0.02):
        self.phase = phase
        self.max_position_pct = max_position_pct
        
        # Tracking for measurement
        self.actual_win_rate = None  # Measure from live
        self.actual_expected_r = None  # Measure from live
    
    def calculate(self, confidence: float, expected_r: float, win_rate: float) -> float:
        """
        Calculate position size using Kelly Criterion.
        
        Formula: Kelly % = (bp - q) / b
        where b = odds (expected_r), p = win_rate, q = 1-p
        """
        
        if self.phase == "track_only":
            # Log what Kelly would have been, but use fixed size
            kelly = self._kelly_formula(expected_r, win_rate)
            print(f"[KELLY TRACK] Would use: {kelly:.4f}, using fixed: {self.max_position_pct}")
            return self.max_position_pct
        
        # Validate inputs
        if expected_r <= 0 or win_rate <= 0 or win_rate >= 1:
            return 0.0
        
        # Calculate raw Kelly
        kelly = self._kelly_formula(expected_r, win_rate)
        
        # Apply safety multipliers
        if self.phase == "eighth_kelly":
            kelly *= 0.125
        elif self.phase == "quarter_kelly":
            kelly *= 0.25
        else:
            kelly *= 0.125  # Default to conservative
        
        # Apply confidence adjustment (don't size up on low confidence)
        kelly *= min(1.0, confidence / 0.7)
        
        # Enforce limits
        kelly = max(0, min(kelly, self.max_position_pct))
        
        return kelly
    
    def _kelly_formula(self, expected_r: float, win_rate: float) -> float:
        """Standard Kelly formula."""
        p = win_rate
        q = 1 - p
        b = expected_r
        
        kelly = (b * p - q) / b
        return kelly
    
    def update_measurements(self, actual_outcomes: list):
        """
        Update measured win rate and expected R from actual trades.
        Call this after each trade closes.
        """
        if not actual_outcomes:
            return
        
        wins = sum(1 for o in actual_outcomes if o["realized_r"] > 0)
        self.actual_win_rate = wins / len(actual_outcomes)
        
        self.actual_expected_r = np.mean([o["realized_r"] for o in actual_outcomes])
```

### 6.5.3 Using Kelly in Policy

```python
def calculate_position_size(model_output, kelly_sizer, symbol):
    """Calculate position size in policy layer."""
    
    # Get from model output
    confidence = model_output["confidence"]
    expected_r = model_output["expected_r"]
    
    # Win rate comes from calibration or historical
    win_rate = get_measured_win_rate(symbol) or 0.45  # Default if no data
    
    # Get symbol max
    symbol_max = get_symbol_max_position(symbol)
    
    # Calculate
    kelly_pct = kelly_sizer.calculate(confidence, expected_r, win_rate)
    
    return min(kelly_pct, symbol_max)
```

---

## 6.6 Adaptive Stop Loss

### 6.6.1 The Problem

Fixed ATR multipliers don't adapt to regime. In chaotic markets, stops get hit by noise. In stable markets, they're too wide.

### 6.6.2 Regime-Aware Stop Multipliers

```python
def get_stop_multiplier(regime: Regime, symbol_profile: dict) -> float:
    """
    Get ATR multiplier based on regime and symbol.
    
    Key insight: In TRANSITION or HIGH_VOL_CHAOTIC, WIDEN STOPS is wrong.
    The correct answer is NO_TRADE.
    """
    
    # Base multipliers by regime
    regime_mult = {
        Regime.TREND_UP: 2.0,
        Regime.TREND_DOWN: 2.0,
        Regime.RANGE: 1.5,
        Regime.TRANSITION: 99.0,  # Force no-trade instead of wide stop
    }
    
    base = regime_mult.get(regime, 2.0)
    
    # Don't widen in transition - just block the trade
    if regime == Regime.TRANSITION:
        return base  # Will trigger no-trade
    
    # Symbol volatility adjustment
    vol_profile = symbol_profile.get("volatility_profile", "medium")
    
    vol_adj = {
        "very_low": 0.8,
        "low": 0.9,
        "medium": 1.0,
        "high": 1.3,
        "very_high": 1.5,
    }
    
    return base * vol_adj.get(vol_profile, 1.0)
```

### 6.6.3 Volatility Gap Protection

```python
def calculate_stop_with_gap_protection(
    entry_price: float,
    side: str,
    atr: float,
    regime: Regime,
    recent_gaps: list[float]
) -> float:
    """
    Calculate stop with protection against gap moves.
    
    If recent gaps exceed the stop distance, use gap + buffer.
    """
    
    # Get base stop
    multiplier = get_stop_multiplier(regime, symbol_profile)
    base_stop_distance = atr * multiplier
    
    # Check for recent gaps
    max_gap = max(recent_gaps) if recent_gaps else 0
    
    if max_gap > base_stop_distance:
        # Use gap distance + buffer rather than widening stop
        stop_distance = max_gap * 1.2
    else:
        stop_distance = base_stop_distance
    
    # Calculate actual price
    if side == "LONG":
        return entry_price - stop_distance
    else:
        return entry_price + stop_distance
```

### 6.6.4 Using in Simulation Truth Layer

```python
def run_simulation_with_adaptive_stops(
    market_data,
    regime_signal,
    symbol_profile,
    config
):
    """Run simulation with regime-aware stop loss."""
    
    # In transition regime, default to no-trade without running simulation
    if regime_signal.regime == Regime.TRANSITION:
        return {
            "best_action": "NO_TRADE",
            "reason": "transition_regime",
            "stop_multiplier": 99.0,
        }
    
    # Otherwise run with adaptive multiplier
    stop_mult = get_stop_multiplier(regime_signal.regime, symbol_profile)
    
    # Inject into simulation config
    sim_config = config.copy()
    sim_config["stop_multiplier"] = stop_mult
    
    return run_simulation(market_data, sim_config)
```

---

## 6.7 Correlation-Aware Portfolio Control

### 6.7.1 The Problem

Going LONG on BTC + 30 highly correlated alts = 31x BTC exposure. Portfolio limits must account for correlation, not just count positions.

### 6.7.2 Pre-Computed Correlation Groups

```python
# Define correlation groups (computed offline, versioned)
CORRELATION_GROUPS = {
    "btc_cluster": {"BTCUSDT", "WBTCUSDT", "BTCB\.USDT"},
    "eth_cluster": {"ETHUSDT", "ETH\.USDT", "ETHB\.USDT"},
    "layer1": {"SOLUSDT", "ADAUSDT", "DOTUSDT", "AVAXUSDT", "MATICUSDT"},
    "defi": {"UNIUSDT", "AAVEUSDT", "MKRUSDT", "SNXUSDT"},
    "meme_coins": {"DOGEUSDT", "SHIBUSDT", "PEPEUSDT"},
}


def get_correlation_group(symbol: str, groups: dict = CORRELATION_GROUPS) -> str:
    """Find which correlation group a symbol belongs to."""
    for group_name, members in groups.items():
        import re
        for member in members:
            if re.match(member, symbol):
                return group_name
    return "uncorrelated"
```

### 6.7.3 Effective Exposure Calculation

```python
class CorrelationAwarePortfolio:
    """Calculate effective exposure accounting for correlation."""
    
    def __init__(self, max_cluster_exposure=0.15, max_direction_exposure=0.25):
        self.max_cluster_exposure = max_cluster_exposure
        self.max_direction_exposure = max_direction_exposure
    
    def calculate_exposure(self, positions: list[dict]) -> dict:
        """
        Calculate effective exposure across all positions.
        
        Args:
            positions: List of {symbol, side, size_pct}
        """
        
        if not positions:
            return {
                "total_long": 0.0,
                "total_short": 0.0,
                "net": 0.0,
                "effective": 0.0,
                "clusters": {},
                "warnings": [],
            }
        
        # Group by side
        long_exposure = sum(p["size_pct"] for p in positions if p["side"] == "LONG")
        short_exposure = sum(p["size_pct"] for p in positions if p["side"] == "SHORT")
        
        # Cluster analysis
        cluster_exposure = {}
        for pos in positions:
            group = get_correlation_group(pos["symbol"])
            if group == "uncorrelated":
                continue
            
            if group not in cluster_exposure:
                cluster_exposure[group] = 0.0
            cluster_exposure[group] += pos["size_pct"]
        
        # Check warnings
        warnings = []
        
        for cluster, exposure in cluster_exposure.items():
            if exposure > self.max_cluster_exposure:
                warnings.append(f"CLUSTER: {cluster} at {exposure:.1%} exceeds {self.max_cluster_exposure:.1%}")
        
        net = long_exposure - short_exposure
        effective = long_exposure + short_exposure  # Simplified
        
        return {
            "total_long": long_exposure,
            "total_short": short_exposure,
            "net": net,
            "effective": effective,
            "clusters": cluster_exposure,
            "warnings": warnings,
        }
    
    def should_allow_new_position(self, new_pos: dict, current_positions: list) -> tuple[bool, str]:
        """
        Check if new position should be allowed.
        
        Returns: (allowed, reason)
        """
        
        all_positions = current_positions + [new_pos]
        exposure = self.calculate_exposure(all_positions)
        
        # Check cluster limits
        new_group = get_correlation_group(new_pos["symbol"])
        if new_group != "uncorrelated":
            current_cluster_exp = exposure["clusters"].get(new_group, 0.0)
            new_total = current_cluster_exp + new_pos["size_pct"]
            
            if new_total > self.max_cluster_exposure:
                return False, f"cluster_{new_group}_limit"
        
        # Check direction limits
        if new_pos["side"] == "LONG":
            new_long = exposure["total_long"] + new_pos["size_pct"]
            if new_long > self.max_direction_exposure:
                return False, "long_direction_limit"
        else:
            new_short = exposure["total_short"] + new_pos["size_pct"]
            if new_short > self.max_direction_exposure:
                return False, "short_direction_limit"
        
        return True, "allowed"
```

---

## 6.8 Order Book Analysis (Phase 3 - Aggressive Scalp Only)

### 6.8.1 When to Use

Order book analysis is ONLY relevant for aggressive scalp (15m/5m timeframes). For swing and regular scalp, the information is already reflected in price data.

### 6.8.2 Implementation

```python
class OrderBookAnalyzer:
    """
    Analyze order book for aggressive scalp decisions.
    
    Note: Requires real-time order book data stream.
    """
    
    def __init__(self, min_spread_pct=0.001, min_depth_usd=10000):
        self.min_spread_pct = min_spread_pct
        self.min_depth_usd = min_depth_usd
    
    def analyze(self, orderbook: dict) -> dict:
        """
        Analyze order book state.
        
        Args:
            orderbook: {bids: [(price, qty)], asks: [(price, qty)]}
        """
        
        bid_price, bid_qty = orderbook["bids"][0]
        ask_price, ask_qty = orderbook["asks"][0]
        
        mid_price = (bid_price + ask_price) / 2
        spread = ask_price - bid_price
        spread_pct = spread / mid_price
        
        # Calculate total depth
        bid_depth = sum(qty for _, qty in orderbook["bids"][:5])
        ask_depth = sum(qty for _, qty in orderbook["asks"][:5])
        
        # Imbalance
        total = bid_depth + ask_depth
        imbalance = (bid_depth - ask_depth) / total if total > 0 else 0
        
        # Determine if favorable
        status = self._determine_status(spread_pct, bid_depth, ask_depth)
        
        return {
            "spread_pct": spread_pct,
            "bid_depth": bid_depth,
            "ask_depth": ask_depth,
            "imbalance": imbalance,
            "status": status,  # FAVORABLE | UNFAVORABLE | MARGINAL
            "execution_risk": "LOW" if status == "FAVORABLE" else "HIGH",
        }
    
    def _determine_status(self, spread_pct, bid_depth, ask_depth) -> str:
        """Determine if order book state is favorable for trading."""
        
        # Spread too wide
        if spread_pct > self.min_spread_pct * 2:
            return "UNFAVORABLE"
        
        # Insufficient depth
        if bid_depth < self.min_depth_usd or ask_depth < self.min_depth_usd:
            return "UNFAVORABLE"
        
        # Marginal
        if spread_pct > self.min_spread_pct or min(bid_depth, ask_depth) < self.min_depth_usd * 2:
            return "MARGINAL"
        
        return "FAVORABLE"
```

### 6.8.3 Integration with Aggressive Scalp

```python
def aggressive_scalp_decision(model_output, orderbook_analyzer, orderbook_data):
    """
    Make aggressive scalp decision with order book check.
    """
    
    # First check order book
    ob_analysis = orderbook_analyzer.analyze(orderbook_data)
    
    if ob_analysis["status"] == "UNFAVORABLE":
        return {
            "action": "NO_TRADE",
            "reason": "unfavorable_orderbook",
            "details": ob_analysis,
        }
    
    if ob_analysis["status"] == "MARGINAL":
        # Require stronger model signal
        if model_output["confidence"] < 0.85:
            return {
                "action": "NO_TRADE",
                "reason": "marginal_orderbook_low_confidence",
                "details": ob_analysis,
            }
    
    # If order book favorable, proceed with model decision
    return {
        "action": model_output["recommended_action"],
        "reason": "model_decision",
        "orderbook": ob_analysis,
    }
```

---

## 6.9 Alpha Thesis to Mode Mapping

### Purpose

This section connects alpha hypotheses defined in `alpha_thesis_validation_plan.md` to the V7 mode architecture. Each alpha hypothesis is a research candidate, not a locked profitable truth.

### Mapping Table

| Alpha ID | Description | Likely Modes | Not Recommended Modes | Required Features | Required Simulation Outputs | Required Cost Assumptions | Validation Gate | Rejection Conditions | Owner |
|----------|-------------|-------------|----------------------|-------------------|----------------------------|--------------------------|-----------------|---------------------|-------|
| ALTCOIN_DELAY | BTC or major coin movement followed by delayed altcoin reaction | SWING, SCALP | AGGRESSIVE_SCALP | BTC/altcoin return correlation, cross-sectional momentum, volume ratio | long_R_net, short_R_net, best_action_label, no_trade_quality, regret_r | Fee + slippage; funding deferred for perps | Walk-forward 12-fold, R-multiple > 1.5 median, beats all 3 baselines (random, B&H, naive momentum) | Only works in 1 regime; loses to random baseline; R < 1.0; survivorship bias not addressed | AlphaForge |
| VOLATILITY_COMPRESSION | Low volatility compression followed by breakout or expansion | SCALP, AGGRESSIVE_SCALP | SWING | ATR percentile, volatility ratio, breakout detection, volume expansion | long_R_net, short_R_net, time_to_mfe_bars, exit_efficiency | Fee + slippage; funding not applicable (spot-only) | Breakout success rate > 40%; beats random direction after compression | False breakout dominates; direction randomness untestable without independent signal | AlphaForge |
| FUNDING_DIVERGENCE | Funding/spot/perp divergence suggesting directional pressure or crowded positioning | SWING, SCALP | AGGRESSIVE_SCALP | Funding rate, spot/futures return divergence, open interest delta | long_R_net, short_R_net, funding_cost_r, cost_adjusted_expectancy | **Funding cost model REQUIRED** — cannot promote for perpetuals without it; data availability must be verified first | Directional accuracy > 45%; data availability verified; works on multiple symbols, not just BTC | Data unavailable; directional accuracy < 45%; only works on BTC; funding cost model not documented | AlphaForge |

### Mandatory Mapping Principles

1. **Alpha hypotheses are research candidates, not locked profitable truths.** No alpha is assumed profitable before validation.
2. **Each alpha must be validated per mode independently.** ALTCOIN_DELAY validated for SWING does not imply it works for SCALP.
3. **AlphaForge may propose edge, but V7 promotion gate decides acceptance.** Discovery and acceptance are separate authorities.
4. **Funding Divergence cannot be promoted for perpetuals until the funding cost model is documented** (see `simulation/docs/cost_model.md`).
5. **AGGRESSIVE_SCALP requires stronger cost/slippage/no-trade discipline than SWING** — an alpha that looks promising at 4h may be net-negative at 15m after costs.
6. **Composite signals must be validated independently before combination** (see `alpha_thesis_validation_plan.md` composite rules).

### Integration Points

- Alpha validation results feed into `pipeline/evaluation.md` promotion gates.
- Validated alphas become mode-specific feature inputs during dataset construction (`pipeline/dataset.md`).
- Rejected alphas are archived with rejection reason; they do not block mode promotion but are not usable as evidence.
- Alpha thesis validation is **not** the same as mode promotion. A mode can be promoted with different alpha evidence than what was originally hypothesized.

---

## 7. Phase Implementation Timeline

### Phase 1: Core Mode-Centric (Immediate)

| # | Task | Impact | Difficulty |
|---|------|--------|------------|
| 1 | Separate 3 simulation configs | CRITICAL | Medium |
| 2 | Mode-specific label production | CRITICAL | Medium |
| 3 | 3 separate model artifacts | CRITICAL | Medium |
| 4 | Rule-based regime detector | HIGH | Medium |
| 5 | Regime → labels integration | HIGH | Low |
| 6 | Symbol profiles database | HIGH | Low |
| 7 | Slippage model in simulation | CRITICAL | Medium |
| 8 | Volume-based liquidity filter | MEDIUM | Low |

### Phase 2: Post-Live Data (After 3-6 months)

| # | Task | Impact | Difficulty |
|---|------|--------|------------|
| 9 | Regime-aware policy thresholds | MEDIUM | Medium |
| 10 | Adaptive stop loss | MEDIUM | Medium |
| 11 | Correlation portfolio control | MEDIUM | Medium |
| 12 | Kelly position sizing (measured) | HIGH | Medium |

### Phase 3: System Mature (12+ months)

| # | Task | Impact | Difficulty |
|---|------|--------|------------|
| 13 | Order book analysis (agg scalp only) | MEDIUM | High |
| 14 | Supervised regime classifier | MEDIUM | High |
| 15 | News API (if system stable) | LOW | Very High |

---

## 8. Mode Priority and Implementation Order

### Mode Priority Matrix

| Mode | Business Priority | Research Priority | Threshold Status | AlphaForge Report Type | Promotion Readiness |
|------|------------------|-------------------|-----------------|----------------------|---------------------|
| SCALP | **PRIMARY** | **PRIMARY** | HOLD (empirical evidence required) | Primary research report | Not ready until evidence |
| AGGRESSIVE_SCALP | **PRIMARY** | **PRIMARY** | HOLD (empirical evidence required) | Primary research report | Not ready until evidence |
| SWING | SECONDARY_BASELINE | SECONDARY_BASELINE | LOCKED_INITIAL_BASELINE | Secondary baseline report | Baseline ready; recalibration required after first evidence |

### Key Principles

1. **SCALP and AGGRESSIVE_SCALP are the PRIMARY business/research modes.** V7's main edge search targets shorter-term opportunities, anomaly capture, cost-aware fast reaction, and high-frequency signal validation.

2. **SWING is the SECONDARY_BASELINE / CONTROL mode.** SWING was selected for first implementation because it is safer, lower-noise, and easier to baseline — not because it is the primary product. It serves as a control anchor: if SWING fails on a validated architecture, something is fundamentally wrong. If SWING works, it validates the architecture but does not validate SCALP or AGGRESSIVE_SCALP.

3. **Promotion-readiness and research-priority are independent dimensions.** SWING is more promotion-ready (LOCKED_INITIAL_BASELINE thresholds). SCALP and AGGRESSIVE_SCALP have higher business/research priority but require empirical evidence (HOLD) before threshold lock.

4. **HOLD means "empirical research required" — not "low priority."** Fee, slippage, latency, data quality, overfit, and funding risks make SCALP and AGGRESSIVE_SCALP harder to lock without evidence.

### Implementation Strategy

**Control-first, then primary research:** Build and deploy SWING mode first as the architecture validation baseline. SWING proves the full pipeline (contracts → simulation → labels → features → dataset → model → calibration → policy → risk → runtime) with the lowest risk profile.

Once the architecture is validated via SWING:
- SCALP and AGGRESSIVE_SCALP research accelerates on the proven foundation
- AlphaForge produces primary research reports for SCALP/AGGRESSIVE_SCALP
- Empirical evidence gates determine promotion readiness independently per mode

Building all 3 modes simultaneously:
- Multiplies risk
- Multiplies cost  
- Does NOT multiply returns

The 3 modes should share:
- Feature builder (canonical state)
- Runtime infrastructure
- Portfolio/risk layers

But have independent:
- Simulation configs
- Labels
- Models
- Policy thresholds
- Promotion gates

---

## 9. Expected Score Progression

```
Current V7 (single pipeline):          5.5/10
+ Phase 1 (mode-centric + regime):     6.5/10
+ Phase 1 additions (slippage/symbol): 7.5/10
+ Phase 2 (adaptive features):         8.0/10
+ Phase 3 (advanced):                  8.5/10 (ceiling - market dependent)
```

---

## 10. Files to Update

| Original File | Changes Required |
|---------------|------------------|
| `architecture.md` | Add mode-centric diagram, remove "single model" language |
| `pipeline/labels.md` | Add mode-specific label sections, regime integration |
| `pipeline/model.md` | Change to "3 model artifacts" language |
| `pipeline/features.md` | No changes (features are shared) |
| `pipeline/dataset.md` | Add mode to row structure |
| `pipeline/policy.md` | Add regime-aware threshold modifications |
| `pipeline/evaluation.md` | Add regime-aware evaluation metrics |
| `pipeline/portfolio.md` | Implement correlation control |
| `pipeline/simulation.md` | Add mode configs |
| `runtime/runtime_integration.md` | Add mode router |
| `implementation/master_plan.md` | Update phase order |

---

## 11. Summary: What Makes This Different from Original V7

| Aspect | Original V7 | New V7 Mode-Centric |
|--------|-------------|---------------------|
| Model count | 1 shared | 3 independent |
| Timeframe | 4h fixed | 4h/1h/15m per mode |
| Labels | Single family | 3 mode-specific |
| Simulation | One config | 3 mode configs |
| Regime | Not considered | First-class input |
| Slippage | Assumed constant | Calculated per trade |
| Symbol params | Generic | Per-symbol profiles |
| Position sizing | Fixed | Kelly (Phase 2) |

---

**End of Document**
