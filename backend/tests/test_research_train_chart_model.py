"""
Tests for research/train_chart_model.py::_try_load_base_model
(production audit MEDIUM #9): loading the existing chart model for
incremental training used to be wrapped in a bare `except: pass` -
silently swallowing every failure (including a corrupted model file,
or KeyboardInterrupt/SystemExit) with zero observability. Extracted
into its own function so the exception path can be tested without
running the full (heavy, network/GPU-bound) `train()` pipeline.
"""
import logging

import ml.chart_model as chart_model
from research.train_chart_model import _try_load_base_model


def test_returns_none_without_attempting_a_load_when_no_model_exists(monkeypatch):
    monkeypatch.setattr(chart_model, "is_model_available", lambda: False)
    assert _try_load_base_model() is None


def test_returns_the_loaded_model_when_available_and_loadable(monkeypatch):
    sentinel_model = object()
    monkeypatch.setattr(chart_model, "is_model_available", lambda: True)
    monkeypatch.setattr(chart_model, "MODEL_PATH", "/fake/path/model.keras")

    from tensorflow import keras
    monkeypatch.setattr(keras.models, "load_model", lambda path: sentinel_model)

    assert _try_load_base_model() is sentinel_model


def test_a_corrupted_model_file_is_logged_and_does_not_raise(monkeypatch, caplog):
    monkeypatch.setattr(chart_model, "is_model_available", lambda: True)
    monkeypatch.setattr(chart_model, "MODEL_PATH", "/fake/path/model.keras")

    from tensorflow import keras

    def _broken_load(path):
        raise OSError("corrupted model file")

    monkeypatch.setattr(keras.models, "load_model", _broken_load)

    with caplog.at_level(logging.WARNING, logger="research.train_chart_model"):
        result = _try_load_base_model()

    assert result is None
    assert any("corrupted model file" in record.message for record in caplog.records)
