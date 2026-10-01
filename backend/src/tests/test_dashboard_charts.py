"""Tests for dashboard/charts.py. Pure shaping - no infra."""
from datetime import datetime, timezone

from dashboard.charts import (
    histogram_to_chart_data,
    mapping_to_bar_chart_data,
    mapping_to_pie_chart_data,
    time_series_to_chart_data,
)
from dashboard.models import Histogram, TimeSeries, TimeSeriesPoint


def test_time_series_to_chart_data():
    now = datetime.now(timezone.utc)
    series = TimeSeries(name="confidence", points=[TimeSeriesPoint(timestamp=now, value=0.5)])
    chart_data = time_series_to_chart_data(series)
    assert chart_data["name"] == "confidence"
    assert chart_data["values"] == [0.5]
    assert chart_data["labels"] == [now.isoformat()]


def test_time_series_to_chart_data_empty():
    chart_data = time_series_to_chart_data(TimeSeries(name="empty"))
    assert chart_data["labels"] == []
    assert chart_data["values"] == []


def test_histogram_to_chart_data():
    histogram = Histogram(bin_edges=[0.0, 5.0, 10.0], counts=[3, 7])
    chart_data = histogram_to_chart_data(histogram)
    assert chart_data["labels"] == ["0.00-5.00", "5.00-10.00"]
    assert chart_data["values"] == [3, 7]


def test_mapping_to_pie_chart_data():
    chart_data = mapping_to_pie_chart_data({"BUY": 3, "SELL": 2})
    assert chart_data["labels"] == ["BUY", "SELL"]
    assert chart_data["values"] == [3, 2]


def test_mapping_to_bar_chart_data():
    chart_data = mapping_to_bar_chart_data({"AAPL": 1.5, "MSFT": 2.5})
    assert chart_data["labels"] == ["AAPL", "MSFT"]
    assert chart_data["values"] == [1.5, 2.5]
