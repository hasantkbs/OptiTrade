"""
OptiTrade Analytics & Dashboard Platform — chart-ready data shaping.

Turns the analytics primitives (`TimeSeries`, `Histogram`, plain
label->value dicts) into the flat `{"labels": [...], "values": [...]}`
shape most charting frontends (Chart.js, Recharts, Plotly, ...) expect,
so API consumers never need to understand this platform's internal
Pydantic shapes to render a chart.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

from dashboard.models import Histogram, TimeSeries


def time_series_to_chart_data(series: TimeSeries) -> Dict[str, Any]:
    return {
        "name": series.name,
        "labels": [point.timestamp.isoformat() for point in series.points],
        "values": [point.value for point in series.points],
    }


def histogram_to_chart_data(histogram: Histogram) -> Dict[str, Any]:
    labels = [
        f"{histogram.bin_edges[i]:.2f}-{histogram.bin_edges[i + 1]:.2f}"
        for i in range(len(histogram.bin_edges) - 1)
    ]
    return {"labels": labels, "values": list(histogram.counts)}


def mapping_to_pie_chart_data(mapping: Mapping[str, float]) -> Dict[str, Any]:
    return {"labels": list(mapping.keys()), "values": list(mapping.values())}


def mapping_to_bar_chart_data(mapping: Mapping[str, float]) -> Dict[str, Any]:
    return {"labels": list(mapping.keys()), "values": list(mapping.values())}
