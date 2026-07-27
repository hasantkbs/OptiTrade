"""
OptiTrade Research Lab — backtest fold splitters.

Every voting engine here is already-built and rule-based/statistical
(never retrained per fold - that would require reaching into
production inference, which this package must never do). "Walk-forward"
and "rolling window" therefore mean evaluating the engine's *realized*
historical performance across successive chronological slices, not
re-fitting a model per slice. Each function is a pure splitter: given a
chronological `(timestamp, return_pct)` series, it returns the `Fold`s
`backtesting/engine.py` computes per-fold metrics over.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Tuple

Series = List[Tuple[datetime, float]]


@dataclass
class Fold:
    fold_index: int
    test_start: datetime
    test_end: datetime
    test_series: Series


def walk_forward_splits(series: Series, train_window_days: int, test_window_days: int) -> List[Fold]:
    """Rolls a fixed-size train window forward; each subsequent
    test_window_days-long slice immediately after it becomes one fold.
    Detects whether the engine's performance holds up out-of-sample as
    time progresses, without ever refitting anything."""
    if not series:
        return []

    folds: List[Fold] = []
    cursor = series[0][0]
    end = series[-1][0]
    index = 0

    while True:
        train_end = cursor + timedelta(days=train_window_days)
        test_end = train_end + timedelta(days=test_window_days)
        if train_end > end:
            break
        test_series = [(t, r) for t, r in series if train_end <= t < test_end]
        if test_series:
            folds.append(Fold(fold_index=index, test_start=train_end, test_end=test_end, test_series=test_series))
            index += 1
        cursor += timedelta(days=test_window_days)

    return folds


def rolling_window_splits(series: Series, window_days: int, step_days: int) -> List[Fold]:
    """A fixed-size window slides forward by `step_days` each fold -
    no train/test split, since nothing is being fit; each window is
    simply its own evaluation period."""
    if not series:
        return []

    folds: List[Fold] = []
    cursor = series[0][0]
    end = series[-1][0]
    index = 0

    while cursor < end:
        window_end = cursor + timedelta(days=window_days)
        window_series = [(t, r) for t, r in series if cursor <= t < window_end]
        if window_series:
            folds.append(Fold(fold_index=index, test_start=cursor, test_end=window_end, test_series=window_series))
            index += 1
        cursor += timedelta(days=step_days)

    return folds


def purged_cv_splits(series: Series, n_folds: int, embargo_days: int) -> List[Fold]:
    """Splits the full window into `n_folds` equal-length chronological
    folds, each with an embargo buffer trimmed from its edges (except
    the series' own start/end) so no fold's evaluated period overlaps
    the horizon of samples immediately adjacent to it - the
    purge+embargo technique standard in financial cross-validation to
    avoid leakage between temporally adjacent samples."""
    if not series or n_folds < 1:
        return []

    start = series[0][0]
    end = series[-1][0]
    total_seconds = max((end - start).total_seconds(), 1.0)
    fold_span = timedelta(seconds=total_seconds / n_folds)
    embargo = timedelta(days=embargo_days)

    folds: List[Fold] = []
    for i in range(n_folds):
        fold_start = start + fold_span * i
        fold_end = start + fold_span * (i + 1)
        effective_start = fold_start + embargo if i > 0 else fold_start
        effective_end = fold_end - embargo if i < n_folds - 1 else fold_end
        if effective_start >= effective_end:
            continue
        test_series = [(t, r) for t, r in series if effective_start <= t < effective_end]
        if test_series:
            folds.append(Fold(fold_index=i, test_start=effective_start, test_end=effective_end, test_series=test_series))

    return folds


def stress_test_scenarios(series: Series, shock_pct: float) -> List[Fold]:
    """Applies a uniform synthetic shock to every period's return and
    evaluates degraded performance as a single stress scenario - a
    standard technique for probing how metrics hold up under an
    adverse shift rather than assuming historical conditions repeat."""
    if not series:
        return []
    shocked = [(timestamp, value + shock_pct) for timestamp, value in series]
    return [Fold(fold_index=0, test_start=series[0][0], test_end=series[-1][0], test_series=shocked)]


def out_of_sample_split(series: Series, holdout_ratio: float) -> List[Fold]:
    """A single split: the most recent `holdout_ratio` fraction of the
    series (chronologically) is held out as the out-of-sample test
    fold; everything before it is the (unused, reference-only) in-
    sample portion."""
    if not series:
        return []
    split_index = int(len(series) * (1 - holdout_ratio))
    test_series = series[split_index:]
    if not test_series:
        return []
    return [Fold(fold_index=0, test_start=test_series[0][0], test_end=test_series[-1][0], test_series=test_series)]
