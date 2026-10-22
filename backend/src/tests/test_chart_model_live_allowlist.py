"""Tests for ml/chart_model.py's dynamic live allowlist and
significance-check helper, added when SUPPORTED_SYMBOLS moved from a
hardcoded tuple to a JSON file the weekly retraining job
(research/retrain_chart_models.py) updates without a server restart."""
import json

import ml.chart_model as chart_model


def test_get_supported_symbols_reads_from_the_json_file_when_present(tmp_path, monkeypatch):
    path = tmp_path / "supported_symbols.json"
    path.write_text(json.dumps({"supported_symbols": ["ETH-USD", "BTC-USD"]}))
    monkeypatch.setattr(chart_model, "SUPPORTED_SYMBOLS_PATH", str(path))

    assert chart_model.get_supported_symbols() == ("ETH-USD", "BTC-USD")


def test_get_supported_symbols_falls_back_to_the_snapshot_when_file_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_model, "SUPPORTED_SYMBOLS_PATH", str(tmp_path / "does-not-exist.json"))

    assert chart_model.get_supported_symbols() == chart_model._SUPPORTED_SYMBOLS_SNAPSHOT_2026_10_22


def test_get_supported_symbols_falls_back_to_the_snapshot_on_corrupt_json(tmp_path, monkeypatch):
    path = tmp_path / "supported_symbols.json"
    path.write_text("{not valid json")
    monkeypatch.setattr(chart_model, "SUPPORTED_SYMBOLS_PATH", str(path))

    assert chart_model.get_supported_symbols() == chart_model._SUPPORTED_SYMBOLS_SNAPSHOT_2026_10_22


def test_get_supported_symbols_picks_up_a_change_without_reimporting_the_module(tmp_path, monkeypatch):
    """The whole point of moving to a file: a long-running server
    process (never re-imports ml.chart_model) must see an update the
    weekly retraining job makes while the server keeps running."""
    path = tmp_path / "supported_symbols.json"
    monkeypatch.setattr(chart_model, "SUPPORTED_SYMBOLS_PATH", str(path))

    path.write_text(json.dumps({"supported_symbols": ["BTC-USD"]}))
    assert chart_model.get_supported_symbols() == ("BTC-USD",)

    path.write_text(json.dumps({"supported_symbols": ["BTC-USD", "ETH-USD"]}))
    assert chart_model.get_supported_symbols() == ("BTC-USD", "ETH-USD")


def test_check_window_significance_passes_a_large_clear_gap():
    passes, p_value = chart_model.check_window_significance(n=1000, baseline=0.42, accuracy=0.56)
    assert passes is True
    assert p_value < 0.05


def test_check_window_significance_fails_a_gap_indistinguishable_from_chance():
    passes, p_value = chart_model.check_window_significance(n=50, baseline=0.42, accuracy=0.44)
    assert passes is False
    assert p_value >= 0.05


def test_check_window_significance_fails_when_accuracy_is_below_baseline():
    # A large n with accuracy < baseline must never pass, regardless of
    # what the one-sided p-value alone would say.
    passes, p_value = chart_model.check_window_significance(n=1000, baseline=0.50, accuracy=0.40)
    assert passes is False


def test_check_window_significance_accepts_numpy_int_for_n():
    # retrain_chart_models.py sums classification_report "support"
    # values (numpy int64/float64, not plain Python int) into `n` -
    # scipy's binomtest rejects numpy-typed n outright ("n must be an
    # integer"), so this must coerce rather than pass it through raw.
    import numpy as np
    passes, p_value = chart_model.check_window_significance(
        n=np.int64(1000), baseline=0.42, accuracy=0.56,
    )
    assert passes is True
