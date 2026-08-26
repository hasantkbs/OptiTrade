"""
OptiTrade Analytics & Dashboard Platform — generic analytics primitives.

Time series, distributions, histograms, rolling metrics, and cumulative
metrics - every dashboard module builds its views out of these rather
than each hand-rolling its own aggregation logic.
"""
from __future__ import annotations

import statistics
from datetime import datetime
from typing import List, Sequence, Tuple

from dashboard.models import CumulativeMetric, Distribution, Histogram, RollingMetric, TimeSeries, TimeSeriesPoint


def build_time_series(name: str, points: Sequence[Tuple[datetime, float]]) -> TimeSeries:
    ordered = sorted(points, key=lambda item: item[0])
    return TimeSeries(name=name, points=[TimeSeriesPoint(timestamp=ts, value=value) for ts, value in ordered])


def build_distribution(values: Sequence[float]) -> Distribution:
    values = list(values)
    if not values:
        return Distribution(count=0)
    return Distribution(
        count=len(values),
        mean=statistics.mean(values),
        median=statistics.median(values),
        stdev=statistics.stdev(values) if len(values) > 1 else 0.0,
        minimum=min(values),
        maximum=max(values),
        values=values,
    )


def build_histogram(values: Sequence[float], bins: int = 10) -> Histogram:
    values = list(values)
    if not values or bins < 1:
        return Histogram()

    minimum, maximum = min(values), max(values)
    if minimum == maximum:
        return Histogram(bin_edges=[minimum, maximum], counts=[len(values)])

    bin_width = (maximum - minimum) / bins
    edges = [minimum + i * bin_width for i in range(bins + 1)]
    counts = [0] * bins
    for value in values:
        index = int((value - minimum) / bin_width)
        index = min(index, bins - 1)  # the maximum value falls in the last bin, not a phantom (bins+1)th one
        counts[index] += 1
    return Histogram(bin_edges=edges, counts=counts)


def build_rolling_metric(points: Sequence[Tuple[datetime, float]], window_size: int) -> RollingMetric:
    if window_size < 1:
        raise ValueError("window_size must be at least 1")
    ordered = sorted(points, key=lambda item: item[0])
    values = [value for _, value in ordered]
    timestamps = [ts for ts, _ in ordered]

    rolling_points: List[TimeSeriesPoint] = []
    for i in range(len(values)):
        if i + 1 < window_size:
            continue
        window = values[i + 1 - window_size: i + 1]
        rolling_points.append(TimeSeriesPoint(timestamp=timestamps[i], value=statistics.mean(window)))
    return RollingMetric(window_size=window_size, points=rolling_points)


def build_cumulative_metric(points: Sequence[Tuple[datetime, float]]) -> CumulativeMetric:
    ordered = sorted(points, key=lambda item: item[0])
    cumulative_points: List[TimeSeriesPoint] = []
    running_total = 0.0
    for ts, value in ordered:
        running_total += value
        cumulative_points.append(TimeSeriesPoint(timestamp=ts, value=running_total))
    return CumulativeMetric(points=cumulative_points)
