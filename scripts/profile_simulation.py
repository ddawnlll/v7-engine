"""Detailed breakdown of simulation engine CPU cost."""

import cProfile, pstats, io, time
from simulation.engine.engine import simulate
from simulation.contracts.models import *
import numpy as np

profile = SimulationProfile(
    profile_version='test', mode=TradingMode.SWING, primary_interval='4h',
    max_holding_bars=30, stop_multiplier=2.0, target_multiplier=2.5,
    ambiguity_margin_r=0.2, min_action_edge_r=0.35, no_trade_default=False,
    stop_method='atr', target_method='atr',
    mae_penalty_weight=1.0, cost_penalty_weight=1.0, time_penalty_weight=0.3,
    funding_rate=0.0,
)
candles = [Candle(open=100+i*0.1, high=100+i*0.1+0.5, low=100+i*0.1-0.5, close=100+i*0.1, volume=1000)
           for i in range(40)]

inp = SimulationInput(
    symbol='BTCUSDT', decision_timestamp='2024-01-01T00:00:00Z', mode=TradingMode.SWING,
    primary_interval='4h', entry_price=100.0, atr=2.0,
    future_path=FuturePath(candles=candles, completeness_status='COMPLETE', expected_bars=30),
    profile=profile,
)

# Warmup
_ = simulate(inp)

# Profile
pr = cProfile.Profile()
pr.enable()
for _ in range(50000):
    _ = simulate(inp)
pr.disable()
s = io.StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats('cumtime')
ps.print_stats(15)
print(s.getvalue())