"""Tests for dashboard/analytics.py. Pure math - no infra."""
from datetime import datetime, timedelta, timezone

import pytest

from dashboard.analytics import (
    build_cumulative_metric,
    build_distribution,
    build_histogram,
    build_rolling_metric,
    build_time_series,
)

_NOW = datetime.now(timezone.utc)


def _points(values):
    return [(_NOW + timedelta(days=i), value) for i, value in enumerate(values)]


def test_build_time_series_sorts_by_timestamp():
    unordered = [(_NOW + timedelta(days=1), 2.0), (_NOW, 1.0)]
    series = build_time_series("test", unordered)
    assert series.name == "test"
    assert [point.value for point in series.points] == [1.0, 2.0]


def test_build_time_series_empty():
    series = build_time_series("empty", [])
    assert series.points == []


def test_build_distribution_empty():
    distribution = build_distribution([])
    assert distribution.count == 0
    assert distribution.mean == 0.0


def test_build_distribution_typical():
    distribution = build_distribution([1.0, 2.0, 3.0, 4.0, 5.0])
    assert distribution.count == 5
    assert distribution.mean == 3.0
    assert distribution.median == 3.0
    assert distribution.minimum == 1.0
    assert distribution.maximum == 5.0
    assert distribution.values == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_build_distribution_single_value_has_zero_stdev():
    distribution = build_distribution([5.0])
    assert distribution.stdev == 0.0


def test_build_histogram_empty():
    histogram = build_histogram([])
    assert histogram.bin_edges == []
    assert histogram.counts == []


def test_build_histogram_all_same_value():
    histogram = build_histogram([5.0, 5.0, 5.0])
    assert histogram.counts == [3]


def test_build_histogram_distributes_values_across_bins():
    histogram = build_histogram(list(range(1, 11)), bins=5)
    assert len(histogram.counts) == 5
    assert sum(histogram.counts) == 10


def test_build_histogram_max_value_falls_in_last_bin():
    histogram = build_histogram([0.0, 10.0], bins=2)
    assert histogram.counts == [1, 1]


def test_build_rolling_metric_requires_full_window():
    rolling = build_rolling_metric(_points([1.0, 2.0, 3.0, 4.0]), window_size=2)
    assert len(rolling.points) == 3
    assert rolling.points[0].value == pytest.approx(1.5)
    assert rolling.points[-1].value == pytest.approx(3.5)


def test_build_rolling_metric_rejects_invalid_window():
    with pytest.raises(ValueError):
        build_rolling_metric(_points([1.0]), window_size=0)


def test_build_cumulative_metric():
    cumulative = build_cumulative_metric(_points([1.0, 2.0, 3.0]))
    assert [point.value for point in cumulative.points] == [1.0, 3.0, 6.0]


def test_build_cumulative_metric_empty():
    cumulative = build_cumulative_metric([])
    assert cumulative.points == []
