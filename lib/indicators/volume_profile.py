"""
Volume-weighted indicators: VWAP and volume profile.

Pure math — no state, no adapters, no business logic.
"""

from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class VolumeProfile:
    """Frozen result of a volume profile computation.

    Represents how volume was distributed across price levels
    over the given lookback window.

    Attributes:
        price_bins: Array of bin-centre prices (ascending).
        volume_per_bin: Volume allocated to each bin.
        poc_idx: Index of the Point of Control (bin with max volume).
        vah_idx: Index of the Value Area High (upper ~70% boundary, approx).
        val_idx: Index of the Value Area Low (lower ~70% boundary, approx).
        total_volume: Total volume across all bins.
    """

    price_bins: list[float] = field(default_factory=list)
    volume_per_bin: list[float] = field(default_factory=list)
    poc_idx: int = 0
    vah_idx: int = 0
    val_idx: int = 0
    total_volume: float = 0.0

    @property
    def poc_price(self) -> float | None:
        """Price at the Point of Control (highest-volume bin)."""
        if not self.price_bins or self.poc_idx >= len(self.price_bins):
            return None
        return self.price_bins[self.poc_idx]

    @property
    def vah_price(self) -> float | None:
        """Price at the Value Area High boundary."""
        if not self.price_bins or self.vah_idx >= len(self.price_bins):
            return None
        return self.price_bins[self.vah_idx]

    @property
    def val_price(self) -> float | None:
        """Price at the Value Area Low boundary."""
        if not self.price_bins or self.val_idx >= len(self.price_bins):
            return None
        return self.price_bins[self.val_idx]


def vwap(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
    period: int = 20,
) -> list[float]:
    """Rolling Volume-Weighted Average Price (VWAP).

    Uses the typical price as the per-bar price level:

        tp_i = (high_i + low_i + close_i) / 3
        VWAP_t = sum(tp_i * vol_i) / sum(vol_i)

    over the trailing ``period`` bars ending at index t.

    Args:
        highs: High prices.
        lows: Low prices.
        closes: Close prices.
        volumes: Volume per bar (must be >= 0).
        period: Lookback window (default 20).

    Returns:
        List of VWAP values (same length). First ``period-1`` values
        are NaN. Returns NaN for windows with zero total volume.
    """
    n = len(highs)
    result: list[float] = [float("nan")] * n

    if n < period:
        return result

    for i in range(period - 1, n):
        tp_vol_sum = 0.0
        vol_sum = 0.0
        for j in range(i - period + 1, i + 1):
            tp = (highs[j] + lows[j] + closes[j]) / 3.0
            v = volumes[j] if j < len(volumes) else 0.0
            if v > 0:
                tp_vol_sum += tp * v
                vol_sum += v

        if vol_sum > 0:
            result[i] = tp_vol_sum / vol_sum
        else:
            result[i] = float("nan")

    return result


def compute_volume_profile(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
    num_bins: int = 10,
) -> VolumeProfile:
    """Compute the volume profile over the full input series.

    Divides the price range (min low to max high) into ``num_bins``
    equal-width bins, assigns each bar's volume to the bin that
    contains its typical price, and identifies the Point of Control
    and Value Area boundaries.

    Args:
        highs: High prices.
        lows: Low prices.
        closes: Close prices.
        volumes: Volume per bar.
        num_bins: Number of price bins (default 10).

    Returns:
        ``VolumeProfile`` frozen dataclass with price bins,
        volume distribution, POC, VAH, and VAL.
    """
    n = len(highs)
    if n == 0 or len(lows) == 0 or num_bins < 1:
        return VolumeProfile()

    price_min = min(lows)
    price_max = max(highs)
    if price_max <= price_min:
        return VolumeProfile()

    bin_width = (price_max - price_min) / num_bins
    bin_centres: list[float] = [
        price_min + bin_width * (k + 0.5) for k in range(num_bins)
    ]
    volume_per_bin: list[float] = [0.0] * num_bins
    total_volume = 0.0

    for i in range(n):
        tp = (highs[i] + lows[i] + closes[i]) / 3.0
        vol = volumes[i] if i < len(volumes) else 0.0
        if vol <= 0:
            continue

        # Which bin does tp fall into?
        bin_idx = int((tp - price_min) / bin_width)
        if bin_idx < 0:
            bin_idx = 0
        elif bin_idx >= num_bins:
            bin_idx = num_bins - 1

        volume_per_bin[bin_idx] += vol
        total_volume += vol

    if total_volume == 0:
        return VolumeProfile()

    # Point of Control = bin with maximum volume
    poc_idx = 0
    max_vol = volume_per_bin[0]
    for k in range(1, num_bins):
        if volume_per_bin[k] > max_vol:
            max_vol = volume_per_bin[k]
            poc_idx = k

    # Value Area = bins covering ~70% of total volume around POC
    va_threshold = total_volume * 0.70
    low_idx = poc_idx
    high_idx = poc_idx
    accumulated = volume_per_bin[poc_idx]

    while accumulated < va_threshold:
        expanded = False
        # Try expanding left
        if low_idx > 0:
            next_low_vol = volume_per_bin[low_idx - 1]
        else:
            next_low_vol = -1.0
        # Try expanding right
        if high_idx < num_bins - 1:
            next_high_vol = volume_per_bin[high_idx + 1]
        else:
            next_high_vol = -1.0

        if next_low_vol >= next_high_vol and next_low_vol >= 0:
            low_idx -= 1
            accumulated += volume_per_bin[low_idx]
            expanded = True
        elif next_high_vol >= 0:
            high_idx += 1
            accumulated += volume_per_bin[high_idx]
            expanded = True

        if not expanded:
            break

    return VolumeProfile(
        price_bins=bin_centres,
        volume_per_bin=volume_per_bin,
        poc_idx=poc_idx,
        vah_idx=high_idx,
        val_idx=low_idx,
        total_volume=total_volume,
    )
