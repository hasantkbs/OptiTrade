"""Tests for engines/news/impact.py."""
from engines.news import impact


def test_score_impact_zero_for_neutral_sentiment():
    assert impact.score_impact(0.0) == 0.0


def test_score_impact_is_absolute_value_of_sentiment():
    assert impact.score_impact(0.6) == 0.6
    assert impact.score_impact(-0.6) == 0.6


def test_score_impact_clamped_to_one():
    assert impact.score_impact(1.5) == 1.0
    assert impact.score_impact(-1.5) == 1.0


def test_impact_label_high_for_large_magnitude():
    assert impact.impact_label(0.8) == "HIGH"
    assert impact.impact_label(-0.8) == "HIGH"


def test_impact_label_medium_for_moderate_magnitude():
    assert impact.impact_label(0.4) == "MEDIUM"


def test_impact_label_low_for_small_magnitude():
    assert impact.impact_label(0.1) == "LOW"
