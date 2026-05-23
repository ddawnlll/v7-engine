"""
lib/time — Time and temporal split utilities shared by both systems.
"""

from lib.time.intervals import interval_to_minutes, minutes_to_interval, validate_interval
from lib.time.folds import generate_folds, Fold

__all__ = [
    "interval_to_minutes", "minutes_to_interval", "validate_interval",
    "generate_folds", "Fold",
]
