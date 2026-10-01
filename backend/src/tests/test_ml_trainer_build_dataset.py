"""
Tests for research/ml_trainer.py::build_dataset (production audit
MEDIUM #9): the yfinance fetch inside build_dataset had no exception
handling at all - a single symbol's fetch failure (rate limit,
delisted ticker, network hiccup) propagated straight out of the
`for sym in SYMBOLS` loop in train(), aborting the entire multi-symbol
training data collection and discarding every symbol already
collected. It must now degrade the same way "insufficient history"
already does - an empty result for that one symbol, not a crash - and
log the failure rather than silently discarding it.
"""
import logging

import numpy as np
import pytest

import research.ml_trainer as ml_trainer
from research.ml_trainer import LOOKBACK, build_dataset


class _RaisingTicker:
    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, period):
        raise ConnectionError(f"simulated yfinance failure for {self.symbol}")


def test_a_fetch_failure_returns_empty_arrays_instead_of_raising(monkeypatch):
    monkeypatch.setattr(ml_trainer.yf, "Ticker", _RaisingTicker)

    X, y = build_dataset("BAD_SYM")

    assert isinstance(X, np.ndarray) and X.size == 0
    assert isinstance(y, np.ndarray) and y.size == 0


def test_a_fetch_failure_is_logged_not_silently_swallowed(monkeypatch, caplog):
    monkeypatch.setattr(ml_trainer.yf, "Ticker", _RaisingTicker)

    with caplog.at_level(logging.WARNING, logger="research.ml_trainer"):
        build_dataset("BAD_SYM")

    assert any("BAD_SYM" in record.message for record in caplog.records)


def test_insufficient_history_still_returns_empty_arrays_without_a_warning(monkeypatch, caplog):
    """The pre-existing "not enough history" skip must keep behaving
    exactly as before - only a genuine fetch failure is new/logged."""
    class _ShortHistoryTicker:
        def __init__(self, symbol):
            pass

        def history(self, period):
            import pandas as pd
            return pd.DataFrame({"Close": [1.0] * (LOOKBACK)})  # too short

    monkeypatch.setattr(ml_trainer.yf, "Ticker", _ShortHistoryTicker)

    with caplog.at_level(logging.WARNING, logger="research.ml_trainer"):
        X, y = build_dataset("SHORT_SYM")

    assert X.size == 0 and y.size == 0
    assert caplog.records == []
