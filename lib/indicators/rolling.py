"""
Generic rolling window utilities.

Pure math — no state, no adapters.
"""

from typing import Callable, Sequence, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def rolling_apply(
    values: Sequence[T],
    window: int,
    func: Callable[[list[T]], R],
    min_periods: int | None = None,
) -> list[R | None]:
    """Apply a function to each rolling window.

    Args:
        values: Input sequence.
        window: Window size.
        func: Function that takes a list of window values and returns a result.
        min_periods: Minimum number of observations required (default = window).

    Returns:
        List of results (same length). Prior to min_periods, returns None.
    """
    if min_periods is None:
        min_periods = window

    n = len(values)
    result: list[R | None] = [None] * n
    for i in range(n):
        start = max(0, i - window + 1)
        window_values = list(values[start : i + 1])
        if len(window_values) >= min_periods:
            result[i] = func(window_values)
    return result
