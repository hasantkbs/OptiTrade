"""
Tests for engines/technical/feature_adapter.py.

Most tests use a synthetic, deterministic OHLCV DataFrame (constructed
directly, not fetched) injected by monkeypatching
`engines.technical.feature_adapter.fetch_history` — this gives fast,
reproducible coverage of the cache/compute/write-back logic and the
value mappings (especially EMA-crossover encoding) without depending on
real, ever-changing market data. A final section runs one genuine,
live-network + real-database end-to-end test against a real symbol.
"""
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from engines.technical.config import (
    ALL_FEATURE_NAMES,
    FEATURE_ATR,
    FEATURE_ATR_PCT,
    FEATURE_BEARISH_PATTERN_COUNT,
    FEATURE_BULLISH_PATTERN_COUNT,
    FEATURE_EMA_CROSSOVER,
    FEATURE_MACD_LINE,
    FEATURE_RESISTANCE_PROXIMITY,
    FEATURE_RSI,
    FEATURE_SUPPORT_PROXIMITY,
    FEATURE_TREND_STRENGTH,
    FEATURE_VOLUME_RATIO,
    FEATURE_VWAP_DIFF,
    TechnicalEngineConfig,
)
from engines.technical.feature_adapter import TechnicalFeatureAdapter
from feature_store.config import FeatureStoreConfig
from feature_store.models import FeatureValue
from feature_store.service import FeatureStoreService


def _synthetic_ohlcv(n: int = 120, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    close = 100 + np.cumsum(rng.normal(0.3, 1.5, n))
    high = close + rng.uniform(0.5, 2.0, n)
    low = close - rng.uniform(0.5, 2.0, n)
    open_ = close + rng.uniform(-1.0, 1.0, n)
    volume = rng.uniform(1_000_000, 3_000_000, n)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume}, index=dates
    )


@pytest.fixture
def adapter():
    a = TechnicalFeatureAdapter(config=TechnicalEngineConfig())
    yield a


@pytest.fixture
def symbol():
    return f"TEST-{uuid.uuid4().hex[:12]}"


@pytest.fixture(autouse=True)
def cleanup(adapter, symbol):
    yield
    conn = adapter.feature_store.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", (symbol,))
    finally:
        adapter.feature_store.offline_store._pool.putconn(conn)
    for name in ALL_FEATURE_NAMES:
        adapter.feature_store.online_store._client.delete(f"feature_store:{symbol}:{name}")


# ─────────────────────────────────────────────────────────────────────────
# _compute_all — synthetic, deterministic OHLCV (no network)
# ─────────────────────────────────────────────────────────────────────────

def test_compute_all_returns_empty_dict_when_no_price_data(adapter, symbol, monkeypatch):
    monkeypatch.setattr("engines.technical.feature_adapter.fetch_history", lambda *a, **k: None)
    assert adapter._compute_all(symbol) == {}


def test_compute_all_produces_every_expected_feature(adapter, symbol, monkeypatch):
    monkeypatch.setattr(
        "engines.technical.feature_adapter.fetch_history", lambda *a, **k: _synthetic_ohlcv()
    )
    values = adapter._compute_all(symbol)

    for name in (
        FEATURE_TREND_STRENGTH, FEATURE_EMA_CROSSOVER, FEATURE_MACD_LINE,
        FEATURE_RSI, FEATURE_ATR, FEATURE_ATR_PCT, FEATURE_VOLUME_RATIO,
        FEATURE_VWAP_DIFF, FEATURE_SUPPORT_PROXIMITY, FEATURE_RESISTANCE_PROXIMITY,
        FEATURE_BULLISH_PATTERN_COUNT, FEATURE_BEARISH_PATTERN_COUNT,
    ):
        assert name in values, f"{name} missing from computed features"
        assert isinstance(values[name], float)


def test_compute_all_encodes_ema_crossover_correctly(adapter, symbol, monkeypatch):
    monkeypatch.setattr(
        "engines.technical.feature_adapter.fetch_history", lambda *a, **k: _synthetic_ohlcv()
    )
    monkeypatch.setattr(
        "engines.technical.feature_adapter.calculate_ema_crossover", lambda prices: "GOLDEN_CROSS"
    )
    values = adapter._compute_all(symbol)
    assert values[FEATURE_EMA_CROSSOVER] == 2.0


def test_compute_all_writes_every_feature_to_the_feature_store(adapter, symbol, monkeypatch):
    monkeypatch.setattr(
        "engines.technical.feature_adapter.fetch_history", lambda *a, **k: _synthetic_ohlcv()
    )
    values = adapter._compute_all(symbol)

    for name, value in values.items():
        record = adapter.feature_store.get_latest_feature(symbol, name)
        assert record is not None
        assert record.value == pytest.approx(value)


# ─────────────────────────────────────────────────────────────────────────
# get_features — cache hit / miss orchestration
# ─────────────────────────────────────────────────────────────────────────

def test_get_features_uses_cache_and_never_touches_the_network_when_all_fresh(
    adapter, symbol, monkeypatch
):
    now = datetime.now(timezone.utc)
    for name in ALL_FEATURE_NAMES:
        adapter.feature_store.write_feature(
            FeatureValue(symbol=symbol, feature_name=name, value=1.23, event_timestamp=now)
        )

    def _raise_if_called(*args, **kwargs):
        raise AssertionError("fetch_history should not be called when all features are fresh")

    monkeypatch.setattr("engines.technical.feature_adapter.fetch_history", _raise_if_called)

    resolution = adapter.get_features(symbol)
    assert set(resolution.from_cache) == set(ALL_FEATURE_NAMES)
    assert resolution.computed_fresh == []
    assert all(v == pytest.approx(1.23) for v in resolution.values.values())


def test_get_features_recomputes_when_stale(adapter, symbol, monkeypatch):
    stale_time = datetime.now(timezone.utc) - timedelta(hours=2)
    adapter.feature_store.write_feature(
        FeatureValue(symbol=symbol, feature_name=FEATURE_RSI, value=1.0, event_timestamp=stale_time)
    )
    monkeypatch.setattr(
        "engines.technical.feature_adapter.fetch_history", lambda *a, **k: _synthetic_ohlcv()
    )

    resolution = adapter.get_features(symbol)
    assert FEATURE_RSI in resolution.computed_fresh
    assert FEATURE_RSI not in resolution.from_cache
    assert resolution.values[FEATURE_RSI] != 1.0  # replaced by the freshly computed value


def test_get_features_returns_a_mix_of_cached_and_fresh(adapter, symbol, monkeypatch):
    now = datetime.now(timezone.utc)
    adapter.feature_store.write_feature(
        FeatureValue(symbol=symbol, feature_name=FEATURE_RSI, value=42.0, event_timestamp=now)
    )
    monkeypatch.setattr(
        "engines.technical.feature_adapter.fetch_history", lambda *a, **k: _synthetic_ohlcv()
    )

    resolution = adapter.get_features(symbol)
    assert FEATURE_RSI in resolution.from_cache
    assert resolution.values[FEATURE_RSI] == 42.0
    assert FEATURE_TREND_STRENGTH in resolution.computed_fresh


def test_get_features_returns_empty_when_symbol_has_no_data_at_all(adapter, symbol, monkeypatch):
    monkeypatch.setattr("engines.technical.feature_adapter.fetch_history", lambda *a, **k: None)
    resolution = adapter.get_features(symbol)
    assert resolution.values == {}
    assert resolution.computed_fresh == []


# ─────────────────────────────────────────────────────────────────────────
# Real, live end-to-end (network + Postgres + Redis)
# ─────────────────────────────────────────────────────────────────────────

def test_real_end_to_end_get_features_for_a_real_symbol(adapter):
    resolution = adapter.get_features("AAPL")
    # Real market data availability can vary, but a large, liquid,
    # long-listed symbol like AAPL should always yield at least the
    # core trend/momentum/oscillator features.
    assert FEATURE_RSI in resolution.values
    assert FEATURE_TREND_STRENGTH in resolution.values
    assert 0.0 <= resolution.values[FEATURE_RSI] <= 100.0

    conn = adapter.feature_store.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM feature_store_records WHERE symbol = %s", ("AAPL",))
    finally:
        adapter.feature_store.offline_store._pool.putconn(conn)
    for name in ALL_FEATURE_NAMES:
        adapter.feature_store.online_store._client.delete(f"feature_store:AAPL:{name}")
