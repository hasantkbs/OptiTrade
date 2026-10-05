# ML Candidate Accuracy — Derived Feature Engineering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 32 engineered features (lag/rolling, weekly multi-timeframe, cross-sectional rank, volatility regime) to the ML Training Platform's dataset-build pipeline, then retrain and re-evaluate the XGBoost direction candidate with everything else held fixed, to test whether a richer feature set alone can beat the naive majority-class out-of-sample baseline.

**Architecture:** New pure functions (`ml_training/features/derived.py`) compute each feature category from already-fetched data; a new orchestrator (`ml_training/features/derived_builder.py::DerivedFeatureBuilder`) owns the Feature Store/price-fetcher I/O and merges their output into `derived_*`-prefixed keys; `DatasetBuilder.build()` is the single integration point, restructured to collect a whole calendar day's basket snapshot before computing each symbol's derived features. Nothing in `TechnicalEngine`, the Feature Store schema, or `decision_engine` changes.

**Tech Stack:** Python, pandas/numpy, the existing `ml_training` package, `psycopg2`/PostgreSQL-backed Feature Store (real DB in tests, matching this project's established convention — see Task 2/3 test notes).

**Spec:** `docs/superpowers/specs/2026-10-03-ml-accuracy-derived-features-design.md`

## Global Constraints

- Every commit ends with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Zero change to any existing caller's behavior for the 17 base features — Task 3's regression test is the concrete proof, not just an assertion.
- Zero changes to `TechnicalEngine`, `TechnicalFeatureAdapter`, the live Feature Store schema, or `decision_engine` — this plan is training-side only.
- No new backfill work — every input (base Feature Store history, cached OHLCV) already exists from prior work this session.
- Missing data stays missing (never fabricated/defaulted) at the per-(symbol, day, feature-category) granularity specified in Tasks 1-2.
- Reuse real production indicator math for multi-timeframe (`core.indicators.calculate_rsi`/`calculate_trend_strength`) — no reimplementation of RSI/trend-strength formulas.
- Model scope (one global model across all 22 symbols) and label definition (direction, 5-day horizon, 1.0% band) stay fixed, matching the prior 3 attempts, so the retrain result isolates the effect of the feature set alone.
- Report the real result honestly, whatever it is.

## Review Focus

- **A symbol with only one feature ever written (e.g. a brand-new symbol with just `trend_strength_pct` seeded) must not crash `DerivedFeatureBuilder.compute()`** — every per-feature-name loop in `DerivedFeatureBuilder` must tolerate `get_feature_history` returning `[]` for the other 4 lag/rolling names and 2 volregime names. Covered in Task 2's "partial feature coverage" test.
- **A `day_snapshot` with only 1 symbol (the common case early in a thin test fixture, or a backtest run scoped to a single symbol) must not produce a spurious 100th-percentile rank** — `cross_sectional_features`'s own `_MIN_CROSS_SECTIONAL_PEERS` floor (3) must trigger, not silently compute a rank of 1.0 against a basket of one. Covered in Task 1's cross-sectional tests.
- **A `history` list that is NOT sorted ascending by `event_timestamp` would silently corrupt lag ordering** (lag1 would not actually be "1 record back") — `DerivedFeatureBuilder` must rely on `FeatureStoreService.get_feature_history`'s own documented ascending-order contract, and Task 1's pure-function tests must build their hand-crafted `FeatureRecord` lists in ascending order to match that real contract, not an arbitrary order that would mask a latent bug. Covered in Task 1's lag/rolling tests via explicit ascending fixtures.
- **`calculate_rsi`/`calculate_trend_strength` returning `None` (below their own period floor) must not raise or insert a `None` into the result dict** — Task 1's `multi_timeframe_features` must check for `None` from each call independently (one indicator can floor out before the other in a short series) before adding its key. Covered in Task 1's multi-timeframe boundary tests.
- **Re-running `train_ml_candidate.py` on the same calendar day as the already-committed `docs/ml-candidate-report-2026-10-03.md` must not silently overwrite that file and destroy the prior 3-attempts historical record** — Task 4 adds an explicit, distinctly-named output path for this run rather than relying on `now.date()` alone. Covered in Task 4 Step 1.

---

### Task 1: Derived feature pure functions

**Files:**
- Create: `backend/src/ml_training/features/derived.py`
- Test: `backend/src/tests/test_ml_training_derived_features.py`

**Interfaces:**
- Consumes: `feature_store.models.FeatureRecord` (fields used: `value: float`, `event_timestamp: datetime`); `core.indicators.calculate_rsi(prices: pd.Series, period: int = 14) -> Optional[float]`; `core.indicators.calculate_trend_strength(prices: pd.Series, period: int = 20) -> Optional[float]`.
- Produces (for Task 2):
  - `lag_rolling_features(history: List[FeatureRecord], feature_name: str) -> Dict[str, float]`
  - `multi_timeframe_features(ohlcv: Optional[pd.DataFrame]) -> Dict[str, float]`
  - `cross_sectional_features(symbol_value: Optional[float], basket_values: List[float], feature_name: str) -> Dict[str, float]`
  - `volatility_regime_features(history: List[FeatureRecord], feature_name: str) -> Dict[str, float]`

- [ ] **Step 1: Write the failing tests for `lag_rolling_features`**

```python
# backend/src/tests/test_ml_training_derived_features.py
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from feature_store.models import FeatureRecord
from ml_training.features.derived import (
    cross_sectional_features,
    lag_rolling_features,
    multi_timeframe_features,
    volatility_regime_features,
)

_NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


def _records(values, name="rsi_14", start=_NOW - timedelta(days=9)):
    """Ascending by event_timestamp, one record per day, matching the
    real FeatureStoreService.get_feature_history contract (ascending,
    oldest first)."""
    return [
        FeatureRecord(
            symbol="X", feature_name=name, value=v,
            event_timestamp=start + timedelta(days=i),
        )
        for i, v in enumerate(values)
    ]


def test_lag_rolling_below_floor_of_3_returns_empty():
    history = _records([10.0, 20.0])  # only 2 records
    assert lag_rolling_features(history, "rsi_14") == {}


def test_lag_rolling_computes_lag1_lag3_lag5_when_available():
    # 6 records: today (index 5) plus lag1..lag5 all available
    history = _records([10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
    result = lag_rolling_features(history, "rsi_14")
    assert result["derived_lag1_rsi_14"] == 50.0
    assert result["derived_lag3_rsi_14"] == 30.0
    assert result["derived_lag5_rsi_14"] == 10.0


def test_lag_rolling_omits_a_lag_key_when_not_enough_history():
    # 4 records: lag1/lag3 available, lag5 is not (needs 6)
    history = _records([10.0, 20.0, 30.0, 40.0])
    result = lag_rolling_features(history, "rsi_14")
    assert result["derived_lag1_rsi_14"] == 30.0
    assert result["derived_lag3_rsi_14"] == 10.0
    assert "derived_lag5_rsi_14" not in result


def test_lag_rolling_roll5_mean_and_std_with_exactly_5_records():
    history = _records([10.0, 20.0, 30.0, 40.0, 50.0])
    result = lag_rolling_features(history, "rsi_14")
    assert result["derived_roll5_mean_rsi_14"] == 30.0
    assert result["derived_roll5_std_rsi_14"] == pytest.approx(14.142135, rel=1e-5)


def test_lag_rolling_roll5_uses_fewer_than_5_down_to_floor_of_3():
    history = _records([10.0, 20.0, 30.0])  # exactly floor of 3
    result = lag_rolling_features(history, "rsi_14")
    assert result["derived_roll5_mean_rsi_14"] == 20.0


def test_lag_rolling_uses_feature_name_in_every_key():
    history = _records([10.0, 20.0, 30.0], name="atr_pct")
    result = lag_rolling_features(history, "atr_pct")
    assert "derived_roll5_mean_atr_pct" in result
    assert "derived_roll5_mean_rsi_14" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests/test_ml_training_derived_features.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ml_training.features.derived'` (or `ImportError`).

- [ ] **Step 3: Implement `lag_rolling_features`**

```python
# backend/src/ml_training/features/derived.py
"""
OptiTrade ML Training Platform — derived feature engineering.

Pure, stateless functions only — every one takes already-fetched data
(FeatureRecord history, OHLCV, a basket snapshot) and returns a dict of
new named features. Never fetches anything itself;
`ml_training.features.derived_builder.DerivedFeatureBuilder` owns all
I/O. Every returned key is prefixed `derived_` so it can never collide
with a base Feature Store feature name in the same flat dict.

Missing data stays missing: every function below has its own minimum-
data floor (named per-function) below which it omits the affected keys
(or returns {} entirely) rather than fabricating a value - matching the
project-wide "never fabricate" convention `ml_training.features
.extractor.FeatureExtractor`/`ml_training.labels.generator
.generate_labels` already use.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from core.indicators import calculate_rsi, calculate_trend_strength
from feature_store.models import FeatureRecord

_LAG_DAYS = (1, 3, 5)
_ROLL_WINDOW = 5
_MIN_ROLL_SAMPLES = 3
_MIN_WEEKLY_CLOSES = 20
_WEEKLY_RSI_PERIOD = 14
_WEEKLY_TREND_PERIOD = 20
_MIN_CROSS_SECTIONAL_PEERS = 3
_MIN_VOLREGIME_SAMPLES = 10


def lag_rolling_features(history: List[FeatureRecord], feature_name: str) -> Dict[str, float]:
    """`history` must be ascending by `event_timestamp`, every record's
    `event_timestamp` at-or-before the sample's own `as_of` (the caller's
    responsibility - see `DerivedFeatureBuilder`). `history[-1]` is the
    most recent record at-or-before `as_of` (the "today" value already
    present in the base feature vector); `derived_lag1_<name>` is
    `history[-2]`, `derived_lag3_<name>` is `history[-4]`, etc. Below
    `_MIN_ROLL_SAMPLES` (3) total records, returns `{}` entirely -
    matches the project's "missing stays missing" convention."""
    if len(history) < _MIN_ROLL_SAMPLES:
        return {}

    result: Dict[str, float] = {}
    for lag in _LAG_DAYS:
        index = len(history) - 1 - lag
        if index >= 0:
            result[f"derived_lag{lag}_{feature_name}"] = history[index].value

    window = history[-_ROLL_WINDOW:]
    values = [record.value for record in window]
    result[f"derived_roll5_mean_{feature_name}"] = float(np.mean(values))
    result[f"derived_roll5_std_{feature_name}"] = float(np.std(values))

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests/test_ml_training_derived_features.py -v -k lag_rolling`
Expected: PASS (6 tests)

- [ ] **Step 5: Write the failing tests for `multi_timeframe_features`**

```python
def _weekly_ohlcv(num_weeks, start=_NOW - timedelta(weeks=35)):
    """Oscillating, not monotonic: `calculate_rsi` divides by the
    average loss, so an always-rising series has zero losses -> a
    zero avg_loss -> NaN -> `calculate_rsi` returns `None` even with
    plenty of history. A sine-wave pattern guarantees both gains and
    losses so RSI is actually computable."""
    import math
    dates = pd.date_range(start=start, periods=num_weeks * 7, freq="D", tz="UTC")
    closes = [100.0 + 5.0 * math.sin(i / 3.0) for i in range(len(dates))]
    return pd.DataFrame({"Close": closes}, index=dates)


def test_multi_timeframe_below_floor_of_20_weekly_closes_returns_empty():
    ohlcv = _weekly_ohlcv(num_weeks=10)  # 10 weeks < 20 floor
    assert multi_timeframe_features(ohlcv) == {}


def test_multi_timeframe_none_ohlcv_returns_empty():
    assert multi_timeframe_features(None) == {}


def test_multi_timeframe_empty_ohlcv_returns_empty():
    assert multi_timeframe_features(pd.DataFrame()) == {}


def test_multi_timeframe_computes_both_keys_with_enough_history():
    ohlcv = _weekly_ohlcv(num_weeks=30)  # well above the 20-week floor
    result = multi_timeframe_features(ohlcv)
    assert "derived_weekly_rsi_14" in result
    assert "derived_weekly_trend_strength_pct" in result
    assert isinstance(result["derived_weekly_rsi_14"], float)
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests/test_ml_training_derived_features.py -v -k multi_timeframe`
Expected: FAIL with `NameError`/`ImportError` (function not defined yet).

- [ ] **Step 7: Implement `multi_timeframe_features`**

```python
def multi_timeframe_features(ohlcv: Optional[pd.DataFrame]) -> Dict[str, float]:
    """`ohlcv` must have a 'Close' column and be pre-filtered by the
    caller to rows at-or-before the sample's own `as_of` (see
    `DerivedFeatureBuilder`). Resamples to weekly closes
    (`resample("W").last()`) and calls the real production indicator
    functions on that weekly series - reusing the exact math
    `engines.technical.feature_adapter.TechnicalFeatureAdapter
    ._compute_all` already uses for the daily versions, not a
    reimplementation. `calculate_rsi` needs `len(prices) >= period + 1`
    (15 at the default `period=14`); `calculate_trend_strength` needs
    `len(prices) >= period` (20 at the default `period=20`) - 20 is the
    binding floor. Below `_MIN_WEEKLY_CLOSES` (20) weekly closes after
    resampling, returns `{}` entirely rather than calling either
    function on too short a series. The two indicators are checked for
    `None` independently since one can floor out before the other on a
    series just above 20 weekly points."""
    if ohlcv is None or ohlcv.empty or "Close" not in ohlcv.columns:
        return {}

    weekly = ohlcv["Close"].resample("W").last().dropna()
    if len(weekly) < _MIN_WEEKLY_CLOSES:
        return {}

    result: Dict[str, float] = {}
    rsi = calculate_rsi(weekly, period=_WEEKLY_RSI_PERIOD)
    if rsi is not None:
        result["derived_weekly_rsi_14"] = rsi
    trend = calculate_trend_strength(weekly, period=_WEEKLY_TREND_PERIOD)
    if trend is not None:
        result["derived_weekly_trend_strength_pct"] = trend
    return result
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests/test_ml_training_derived_features.py -v -k multi_timeframe`
Expected: PASS (4 tests)

- [ ] **Step 9: Write the failing tests for `cross_sectional_features`**

```python
def test_cross_sectional_below_floor_of_3_peers_returns_empty():
    assert cross_sectional_features(50.0, [50.0, 60.0], "rsi_14") == {}


def test_cross_sectional_none_symbol_value_returns_empty():
    assert cross_sectional_features(None, [50.0, 60.0, 70.0], "rsi_14") == {}


def test_cross_sectional_computes_percentile_rank():
    # symbol_value=50 is the lowest of 4 values including itself -> rank 0.25
    result = cross_sectional_features(50.0, [50.0, 60.0, 70.0, 80.0], "rsi_14")
    assert result == {"derived_rank_rsi_14": 0.25}


def test_cross_sectional_highest_value_gets_rank_1():
    result = cross_sectional_features(80.0, [50.0, 60.0, 70.0, 80.0], "rsi_14")
    assert result["derived_rank_rsi_14"] == 1.0
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests/test_ml_training_derived_features.py -v -k cross_sectional`
Expected: FAIL (function not defined yet).

- [ ] **Step 11: Implement `cross_sectional_features`**

```python
def cross_sectional_features(
    symbol_value: Optional[float], basket_values: List[float], feature_name: str,
) -> Dict[str, float]:
    """`basket_values` must include `symbol_value` itself when available
    (the caller passes the whole day's basket snapshot including this
    symbol - see `DerivedFeatureBuilder`). Returns this symbol's
    percentile rank (0.0-1.0, 1.0 = highest) among every peer with a
    value for `feature_name` on this day. Below
    `_MIN_CROSS_SECTIONAL_PEERS` (3) symbols total (including this one),
    or when `symbol_value` is `None`, returns `{}` - a rank against 1-2
    peers is not a meaningful cross-sectional signal."""
    if symbol_value is None or len(basket_values) < _MIN_CROSS_SECTIONAL_PEERS:
        return {}
    rank = sum(1 for v in basket_values if v <= symbol_value) / len(basket_values)
    return {f"derived_rank_{feature_name}": rank}
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests/test_ml_training_derived_features.py -v -k cross_sectional`
Expected: PASS (4 tests)

- [ ] **Step 13: Write the failing tests for `volatility_regime_features`**

```python
def test_volregime_below_floor_of_10_returns_empty():
    history = _records([1.0] * 9, name="atr_pct")
    assert volatility_regime_features(history, "atr_pct") == {}


def test_volregime_zero_std_returns_empty():
    history = _records([5.0] * 10, name="atr_pct")  # constant -> std == 0
    assert volatility_regime_features(history, "atr_pct") == {}


def test_volregime_computes_zscore_of_latest_value():
    # 9 values of 1.0, then a final value of 10.0 - a clear positive z-score
    history = _records([1.0] * 9 + [10.0], name="atr_pct")
    result = volatility_regime_features(history, "atr_pct")
    assert result["derived_volregime_atr_pct"] > 2.0
```

- [ ] **Step 14: Run tests to verify they fail**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests/test_ml_training_derived_features.py -v -k volregime`
Expected: FAIL (function not defined yet).

- [ ] **Step 15: Implement `volatility_regime_features`**

```python
def volatility_regime_features(history: List[FeatureRecord], feature_name: str) -> Dict[str, float]:
    """`history` must be ascending by `event_timestamp`, every record's
    `event_timestamp` at-or-before the sample's own `as_of` - same
    contract as `lag_rolling_features`. Returns `derived_volregime_
    <name>`: the z-score of the most recent value (`history[-1]`,
    included in its own window) against the trailing window's own
    mean/std. Below `_MIN_VOLREGIME_SAMPLES` (10) records, or when the
    trailing std is exactly 0.0 (a constant series - a real
    division-by-zero guard, not expected in practice), returns `{}`."""
    if len(history) < _MIN_VOLREGIME_SAMPLES:
        return {}
    values = [record.value for record in history]
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std == 0.0:
        return {}
    latest = values[-1]
    return {f"derived_volregime_{feature_name}": (latest - mean) / std}
```

- [ ] **Step 16: Run the full test file to verify everything passes**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests/test_ml_training_derived_features.py -v`
Expected: PASS (18 tests)

- [ ] **Step 17: Commit**

```bash
git add backend/src/ml_training/features/derived.py backend/src/tests/test_ml_training_derived_features.py
git commit -m "$(cat <<'EOF'
feat: add pure derived-feature functions for ML candidate accuracy

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: DerivedFeatureBuilder orchestrator

**Files:**
- Create: `backend/src/ml_training/features/derived_builder.py`
- Test: `backend/src/tests/test_ml_training_derived_builder.py`

**Interfaces:**
- Consumes: the 4 pure functions from Task 1 (exact signatures above); `feature_store.service.FeatureStoreService.get_feature_history(symbol: str, feature_name: str, start: datetime, end: datetime) -> List[FeatureRecord]` and `.get_default_feature_store_service() -> FeatureStoreService`; `ml_training.labels.generator.PriceFetcher = Callable[[str, datetime, datetime], Optional[pd.DataFrame]]`; `engines.technical.config.FEATURE_RSI`, `FEATURE_MACD_HISTOGRAM`, `FEATURE_VOLUME_RATIO`, `FEATURE_ATR_PCT`, `FEATURE_TREND_STRENGTH`, `FEATURE_BB_BANDWIDTH` (exact string constants, never hardcode the raw literals).
- Produces (for Task 3): `DerivedFeatureBuilder(feature_store: Optional[FeatureStoreService] = None, price_fetcher: Optional[PriceFetcher] = None)` with `.compute(symbol: str, as_of: datetime, day_snapshot: Dict[str, Dict[str, float]]) -> Dict[str, float]`.

This task's tests use the project's established real-Feature-Store integration-test convention (`backend/src/tests/test_ml_training_features.py`/`test_ml_training_datasets.py` both use a real `FeatureStoreService()` against the real Postgres/Redis backing stores, with a throwaway test symbol and a teardown fixture — never a mocked `FeatureStoreService`). Follow that same pattern here, not a fake.

- [ ] **Step 1: Write the failing tests**

```python
# backend/src/tests/test_ml_training_derived_builder.py
"""Tests for ml_training/features/derived_builder.py. Uses the real
PostgreSQL/Redis-backed Feature Store, matching test_ml_training_features
.py's and test_ml_training_datasets.py's established convention."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from engines.technical.config import FEATURE_ATR_PCT, FEATURE_RSI, FEATURE_TREND_STRENGTH
from feature_store.models import FeatureRecord
from feature_store.service import FeatureStoreService
from ml_training.features.derived_builder import DerivedFeatureBuilder

_SYMBOL = "MLDERIVTEST"
_PEER = "MLDERIVPEER"
_NOW = datetime.now(timezone.utc)


def _seed(fs, symbol, feature_name, values, start):
    for i, v in enumerate(values):
        ts = start + timedelta(days=i)
        fs.offline_store.insert(
            FeatureRecord(
                symbol=symbol, feature_name=feature_name, value=v,
                event_timestamp=ts, ingestion_timestamp=ts,
            )
        )


@pytest.fixture
def feature_store():
    fs = FeatureStoreService()
    yield fs
    conn = fs.offline_store._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM feature_store_records WHERE symbol IN (%s, %s)", (_SYMBOL, _PEER),
            )
    finally:
        fs.offline_store._pool.putconn(conn)


def _oscillating_ohlcv(symbol, start, end):
    """Oscillating, not monotonic - see the identical note on
    `_weekly_ohlcv` in test_ml_training_derived_features.py: a
    monotonically rising series makes `calculate_rsi` divide by a
    zero average loss, returning `None` even with plenty of history."""
    import math
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    return pd.DataFrame(
        {"Close": [100.0 + 5.0 * math.sin(i / 3.0) for i in range(len(dates))]}, index=dates,
    )


def test_compute_merges_lag_rolling_and_volregime_keys(feature_store):
    start = _NOW - timedelta(days=29)
    _seed(feature_store, _SYMBOL, FEATURE_RSI, [float(i) for i in range(30)], start)
    _seed(feature_store, _SYMBOL, FEATURE_ATR_PCT, [1.0] * 29 + [5.0], start)

    builder = DerivedFeatureBuilder(feature_store=feature_store, price_fetcher=_oscillating_ohlcv)
    result = builder.compute(_SYMBOL, _NOW, day_snapshot={})

    assert "derived_lag1_rsi_14" in result
    assert "derived_roll5_mean_rsi_14" in result
    assert "derived_volregime_atr_pct" in result


def test_compute_includes_weekly_multi_timeframe_keys_with_a_price_fetcher(feature_store):
    builder = DerivedFeatureBuilder(feature_store=feature_store, price_fetcher=_oscillating_ohlcv)
    result = builder.compute(_SYMBOL, _NOW, day_snapshot={})
    assert "derived_weekly_rsi_14" in result
    assert "derived_weekly_trend_strength_pct" in result


def test_compute_omits_multi_timeframe_keys_with_no_price_fetcher(feature_store):
    builder = DerivedFeatureBuilder(feature_store=feature_store, price_fetcher=None)
    result = builder.compute(_SYMBOL, _NOW, day_snapshot={})
    assert "derived_weekly_rsi_14" not in result
    assert "derived_weekly_trend_strength_pct" not in result


def test_compute_cross_sectional_uses_day_snapshot(feature_store):
    day_snapshot = {
        _SYMBOL: {FEATURE_RSI: 50.0},
        _PEER: {FEATURE_RSI: 60.0},
        "MLDERIVPEER2": {FEATURE_RSI: 70.0},
    }
    builder = DerivedFeatureBuilder(feature_store=feature_store, price_fetcher=None)
    result = builder.compute(_SYMBOL, _NOW, day_snapshot=day_snapshot)
    assert result["derived_rank_rsi_14"] == pytest.approx(1 / 3)


def test_compute_tolerates_a_symbol_with_only_one_feature_ever_written(feature_store):
    """A symbol with only trend_strength_pct seeded (the other 4 lag/
    rolling names and 2 volregime names have zero history) must not
    raise - every per-feature-name loop must tolerate an empty history
    list for the features that were never written."""
    _seed(feature_store, _SYMBOL, FEATURE_TREND_STRENGTH, [1.0, 2.0, 3.0], _NOW - timedelta(days=2))
    builder = DerivedFeatureBuilder(feature_store=feature_store, price_fetcher=None)
    result = builder.compute(_SYMBOL, _NOW, day_snapshot={})
    assert "derived_roll5_mean_trend_strength_pct" in result
    assert "derived_roll5_mean_rsi_14" not in result


def test_builder_defaults_to_real_feature_store():
    builder = DerivedFeatureBuilder()
    assert isinstance(builder.feature_store, FeatureStoreService)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests/test_ml_training_derived_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ml_training.features.derived_builder'`.

- [ ] **Step 3: Implement `DerivedFeatureBuilder`**

```python
# backend/src/ml_training/features/derived_builder.py
"""
OptiTrade ML Training Platform — derived feature orchestration.

Owns the FeatureStoreService + PriceFetcher dependencies; fetches
exactly what each pure function in `ml_training.features.derived`
needs and merges their output into one `derived_*`-prefixed dict. The
only component in this package that both fetches AND computes -
deliberately kept separate from `ml_training.features.extractor
.FeatureExtractor` (which only ever fetches, never computes) so that
boundary stays honest.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional

from engines.technical.config import (
    FEATURE_ATR_PCT,
    FEATURE_BB_BANDWIDTH,
    FEATURE_MACD_HISTOGRAM,
    FEATURE_RSI,
    FEATURE_TREND_STRENGTH,
    FEATURE_VOLUME_RATIO,
)
from feature_store.service import FeatureStoreService, get_default_feature_store_service
from ml_training.features.derived import (
    cross_sectional_features,
    lag_rolling_features,
    multi_timeframe_features,
    volatility_regime_features,
)
from ml_training.labels.generator import PriceFetcher

_LAG_ROLLING_FEATURE_NAMES = [
    FEATURE_RSI, FEATURE_MACD_HISTOGRAM, FEATURE_VOLUME_RATIO, FEATURE_ATR_PCT, FEATURE_TREND_STRENGTH,
]
_VOLREGIME_FEATURE_NAMES = [FEATURE_ATR_PCT, FEATURE_BB_BANDWIDTH]
_CROSS_SECTIONAL_FEATURE_NAMES = [FEATURE_RSI, FEATURE_VOLUME_RATIO, FEATURE_TREND_STRENGTH]

_LAG_ROLLING_LOOKBACK_DAYS = 10
_VOLREGIME_LOOKBACK_DAYS = 30
_MULTI_TIMEFRAME_LOOKBACK_WEEKS = 30


class DerivedFeatureBuilder:
    """`price_fetcher` is `Optional` so this class can be constructed and
    used (for every category except multi-timeframe) without one - the
    multi-timeframe keys are simply omitted when no `price_fetcher` is
    given, following the same "missing stays missing" convention as
    every other category."""

    def __init__(
        self,
        feature_store: Optional[FeatureStoreService] = None,
        price_fetcher: Optional[PriceFetcher] = None,
    ) -> None:
        self.feature_store = feature_store or get_default_feature_store_service()
        self.price_fetcher = price_fetcher

    def compute(
        self, symbol: str, as_of: datetime, day_snapshot: Dict[str, Dict[str, float]],
    ) -> Dict[str, float]:
        result: Dict[str, float] = {}

        for name in _LAG_ROLLING_FEATURE_NAMES:
            history = self.feature_store.get_feature_history(
                symbol, name, as_of - timedelta(days=_LAG_ROLLING_LOOKBACK_DAYS), as_of,
            )
            result.update(lag_rolling_features(history, name))

        for name in _VOLREGIME_FEATURE_NAMES:
            history = self.feature_store.get_feature_history(
                symbol, name, as_of - timedelta(days=_VOLREGIME_LOOKBACK_DAYS), as_of,
            )
            result.update(volatility_regime_features(history, name))

        for name in _CROSS_SECTIONAL_FEATURE_NAMES:
            symbol_value = day_snapshot.get(symbol, {}).get(name)
            basket_values = [values[name] for values in day_snapshot.values() if name in values]
            result.update(cross_sectional_features(symbol_value, basket_values, name))

        if self.price_fetcher is not None:
            ohlcv = self.price_fetcher(
                symbol, as_of - timedelta(weeks=_MULTI_TIMEFRAME_LOOKBACK_WEEKS), as_of,
            )
            result.update(multi_timeframe_features(ohlcv))

        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests/test_ml_training_derived_builder.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/src/ml_training/features/derived_builder.py backend/src/tests/test_ml_training_derived_builder.py
git commit -m "$(cat <<'EOF'
feat: add DerivedFeatureBuilder orchestrator for ML candidate accuracy

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Wire DerivedFeatureBuilder into DatasetBuilder + zero-behavior-change regression test

**Files:**
- Modify: `backend/src/ml_training/datasets/builder.py:37-102`
- Test: `backend/src/tests/test_ml_training_datasets.py` (add tests; existing tests must keep passing unmodified)

**Interfaces:**
- Consumes: `DerivedFeatureBuilder` from Task 2 (exact constructor/`.compute()` signature above).
- Produces: `DatasetBuilder.__init__(..., derived_feature_builder: Optional[DerivedFeatureBuilder] = None)`; `DatasetBuilder.build()`'s returned `TrainingSample.features` now contains the 17 base keys plus whichever `derived_*` keys cleared their category's floor — same return type as today, just richer dicts.

This task's test additions use the project's established real-Feature-Store integration-test convention already present in `test_ml_training_datasets.py` (the `feature_store`/`_builder`/`_rising` fixtures already defined at the top of that file) — reuse them, don't duplicate.

- [ ] **Step 1: Write the failing regression test**

Add to `backend/src/tests/test_ml_training_datasets.py` (reusing the file's existing `feature_store`, `_builder`, `_rising`, and `_SYMBOL` fixtures defined at the top):

```python
def test_build_adds_derived_features_without_changing_base_feature_values(feature_store):
    """The single most important test in this plan: with
    DerivedFeatureBuilder wired in by default, every existing base-
    feature behavior (sample count, the 17-base-feature value itself)
    stays byte-for-byte identical to today - only new derived_* keys are
    ever added, nothing already there is removed or altered."""
    now = datetime.now(timezone.utc)
    builder = _builder(feature_store)
    samples, version = builder.build(
        [_SYMBOL], DatasetType.TRADER, now - timedelta(days=25), now - timedelta(days=20), step_days=1,
    )

    # Same sample count as test_build_produces_samples_for_every_symbol_day_horizon
    assert len(samples) == 6
    for sample in samples:
        # The fixture seeds FEATURE_TREND_STRENGTH=3.0 for every one of its
        # 15 backdated rows - this value must be completely unchanged.
        assert sample.features[FEATURE_TREND_STRENGTH] == 3.0
        # Any derived_* key present is an ADDITION, never a replacement of
        # the base key - the base key must always still be there too.
        for key in sample.features:
            assert key == FEATURE_TREND_STRENGTH or key.startswith("derived_")


def test_build_derived_feature_builder_is_constructed_by_default():
    builder = DatasetBuilder()
    from ml_training.features.derived_builder import DerivedFeatureBuilder
    assert isinstance(builder.derived_feature_builder, DerivedFeatureBuilder)


def test_build_accepts_an_injected_derived_feature_builder(feature_store):
    """Confirms the injection point works for testability - a builder
    that always returns {} must leave samples with ONLY the base key,
    proving the integration point is exactly where this test (and the
    default-wiring test above) expect it."""
    class _EmptyDerivedBuilder:
        def compute(self, symbol, as_of, day_snapshot):
            return {}

    now = datetime.now(timezone.utc)
    from ml_training.features.extractor import FeatureExtractor
    builder = DatasetBuilder(
        feature_extractor=FeatureExtractor(feature_store=feature_store),
        config=MLTrainingConfig(trader_horizons_days=[3]),
        price_fetcher=_rising,
        derived_feature_builder=_EmptyDerivedBuilder(),
    )
    samples, _ = builder.build(
        [_SYMBOL], DatasetType.TRADER, now - timedelta(days=25), now - timedelta(days=20), step_days=1,
    )
    for sample in samples:
        assert set(sample.features.keys()) == {FEATURE_TREND_STRENGTH}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests/test_ml_training_datasets.py -v -k derived`
Expected: FAIL — `DatasetBuilder` has no `derived_feature_builder` attribute yet, and `build()` doesn't add any `derived_*` keys.

- [ ] **Step 3: Restructure `DatasetBuilder.__init__` and `.build()`**

Replace lines 37-45 (the `__init__` method) in `backend/src/ml_training/datasets/builder.py`:

```python
    def __init__(
        self,
        feature_extractor: Optional[FeatureExtractor] = None,
        config: Optional[MLTrainingConfig] = None,
        price_fetcher: Optional[PriceFetcher] = None,
        derived_feature_builder: Optional[DerivedFeatureBuilder] = None,
    ) -> None:
        self.config = config or MLTrainingConfig.from_env()
        self.feature_extractor = feature_extractor or FeatureExtractor()
        self.price_fetcher: PriceFetcher = price_fetcher or fetch_price_history_range
        self.derived_feature_builder = derived_feature_builder or DerivedFeatureBuilder(
            feature_store=self.feature_extractor.feature_store, price_fetcher=self.price_fetcher,
        )
```

Add the import at the top of the file (alongside the existing `ml_training.features.extractor` import):

```python
from ml_training.features.derived_builder import DerivedFeatureBuilder
```

Replace the `build()` method's per-cursor-day loop body (currently lines 65-88, the `while cursor <= end:` block) with:

```python
        cursor = start
        while cursor <= end:
            day_vectors: Dict[str, Dict[str, float]] = {}
            for symbol in symbols:
                # respect_ingestion_time=True: this is the one production
                # path that turns a historical as_of into training data, so
                # it must not be fed a feature value backfilled/recomputed
                # after the fact - see FeatureExtractor.extract's docstring.
                vector = self.feature_extractor.extract(symbol, cursor, respect_ingestion_time=True)
                if vector.values:
                    day_vectors[symbol] = vector.values

            for symbol, base_values in day_vectors.items():
                derived_values = self.derived_feature_builder.compute(symbol, cursor, day_vectors)
                combined_values = {**base_values, **derived_values}
                feature_names_seen.update(combined_values.keys())

                for horizon_days in horizons:
                    label_set = generate_labels(
                        symbol, cursor, horizon_days, combined_values, self.config, self.price_fetcher,
                    )
                    if label_set is None:
                        continue
                    samples.append(
                        TrainingSample(
                            symbol=symbol, as_of=cursor, horizon_days=horizon_days,
                            features=combined_values, labels=label_set,
                        )
                    )
            cursor += timedelta(days=step_days)
```

Add `Dict` to the existing `typing` import line (`from typing import List, Optional, Tuple` → `from typing import Dict, List, Optional, Tuple`).

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests/test_ml_training_datasets.py -v -k derived`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full existing test file to confirm zero regressions**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests/test_ml_training_datasets.py -v`
Expected: PASS (all tests, including every test that existed before this task — `test_build_produces_samples_for_every_symbol_day_horizon`, `test_build_skips_days_with_no_features`, `test_build_is_point_in_time_correct_no_leakage`, `test_build_excludes_a_same_day_backfilled_feature_from_a_historical_sample`, `test_build_skips_samples_when_label_generation_fails`, `test_build_multiple_horizons_produces_a_sample_per_horizon`, and the `service.py` tests below them).

- [ ] **Step 6: Commit**

```bash
git add backend/src/ml_training/datasets/builder.py backend/src/tests/test_ml_training_datasets.py
git commit -m "$(cat <<'EOF'
feat: wire DerivedFeatureBuilder into DatasetBuilder with zero base-feature regression

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Retrain and evaluate with the expanded feature set; honest report

**Files:**
- Modify: `backend/src/scripts/train_ml_candidate.py:65-66` (add a report-path override constant), `:220-223` (use it)

**Interfaces:**
- Consumes: `DatasetBuilder` from Task 3 (its default construction now automatically wires in `DerivedFeatureBuilder` — no other change needed in this script, since `MLTrainingService.run_training_job`, `ModelEvaluator.evaluate`, and `_samples_to_arrays` are all already feature-name-agnostic, per `FeatureExtractor`'s own "auto-discovers... no code change needed" design established earlier this session).
- Produces: a new dated report at `docs/ml-candidate-report-2026-10-03-derived-features.md`, plus a real registered `CANDIDATE` model in `ml_training_model_registry` trained on the 49-feature set (17 base + up to 32 derived).

**This task runs a real, long-running (likely tens of minutes), read-only-against-production training job.** Run it in the background with patient polling, matching this project's established pattern for the Feature Store backfill and the two prior `train_ml_candidate.py` runs.

- [ ] **Step 1: Add a distinct output-path override so this run never collides with the already-committed `docs/ml-candidate-report-2026-10-03.md`**

In `backend/src/scripts/train_ml_candidate.py`, change line 66 (just after `HORIZON_DAYS = 5`):

```python
HORIZON_DAYS = 5  # matches research/ml_trainer.py's FORWARD_DAYS - fair comparison with xgb_signal_model_oos_test
REPORT_FILENAME_SUFFIX = os.getenv("TRAIN_ML_CANDIDATE_REPORT_SUFFIX", "")
```

Add `import os` to the existing import block near the top of the file if not already present (check — `from __future__ import annotations` and `import sys` are already there; `os` is not, per the file as read during planning).

Change the report-writing line (currently `with open(f"../../docs/ml-candidate-report-{now.date().isoformat()}.md", "w") as f:`) to:

```python
    report_path = f"../../docs/ml-candidate-report-{now.date().isoformat()}{REPORT_FILENAME_SUFFIX}.md"
    with open(report_path, "w") as f:
```

This defaults to today's exact prior behavior (`REPORT_FILENAME_SUFFIX=""` when the env var is unset) — zero behavior change for any future plain run of this script — and lets this specific task set the suffix explicitly.

- [ ] **Step 2: Run the full test suite once to confirm this script-level change breaks nothing**

Run: `cd backend && /home/mayasoft/app/OptiTrade/venv/bin/python -m pytest src/tests -q`
Expected: PASS (no test exercises `train_ml_candidate.py` directly — it's a script, not an importable module under test — so this run confirms the rest of the suite, including Tasks 1-3's new tests, is still green).

- [ ] **Step 3: Commit the script change**

```bash
git add backend/src/scripts/train_ml_candidate.py
git commit -m "$(cat <<'EOF'
feat: add report-path override to train_ml_candidate.py

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Run the real retrain-and-evaluate job in the background**

Run (from `backend/`, with the project venv, in the background — this is the same long-running/read-only-against-production pattern as the prior two `train_ml_candidate.py` runs and the `decision_engine` backtest's real run):

```bash
cd backend/src && TRAIN_ML_CANDIDATE_REPORT_SUFFIX=-derived-features /home/mayasoft/app/OptiTrade/venv/bin/python scripts/train_ml_candidate.py
```

Poll patiently (this took multiple minutes in the two prior runs this session; it will take longer now with 49 features instead of 17 — budget up to 20-30 minutes before treating it as stuck). Do not abort early.

- [ ] **Step 5: Verify the report was written to the distinct path and read it**

Run: `cat docs/ml-candidate-report-2026-10-03-derived-features.md` (from the repo root)
Expected: a report in the same table format as `docs/ml-candidate-report-2026-10-03.md` (Accuracy/Majority baseline/Precision/Recall, train/held-out window dates, held-out sample count), with the model now trained on up to 49 features instead of 17.

Also confirm the prior file is untouched: `git status` must show `docs/ml-candidate-report-2026-10-03.md` as unmodified, and `docs/ml-candidate-report-2026-10-03-derived-features.md` as a new, untracked file.

- [ ] **Step 6: Write the honest summary note at the top of the new report**

Prepend to the top of `docs/ml-candidate-report-2026-10-03-derived-features.md` (above the `# ML Candidate Report` heading the script already wrote), following the same "supersedes/historical-record" framing `docs/ml-candidate-report-2026-10-03.md` itself already uses for its predecessor:

```markdown
# ML Candidate Report — 2026-10-03 (derived features attempt)

Retraining against the same 2-year backfilled Feature Store, train window,
held-out window, label (direction, horizon_days=5, 1.0% band), and 22-symbol
basket as `docs/ml-candidate-report-2026-10-03.md`'s 3rd attempt — the ONLY
change is 32 new engineered features (lag/rolling, weekly multi-timeframe,
cross-sectional rank, volatility regime; see
`docs/superpowers/specs/2026-10-03-ml-accuracy-derived-features-design.md`)
added alongside the original 17, per this sub-project's own Global
Constraint of holding model scope and label definition fixed to isolate
the effect of the feature set alone. `docs/ml-candidate-report-2026-10-03
.md` is NOT overwritten and remains the historical record of the
pre-derived-features attempts.

```

(Leave the script's own auto-generated content below this note exactly as written — do not edit the numbers it produced.)

- [ ] **Step 7: Commit the new report**

```bash
git add docs/ml-candidate-report-2026-10-03-derived-features.md
git commit -m "$(cat <<'EOF'
docs: ML candidate retrain report with derived features

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
