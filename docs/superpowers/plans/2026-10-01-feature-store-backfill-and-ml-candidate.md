# Feature Store Backfill & ML Candidate Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backfill the Feature Store with ~2 years of historical point-in-time technical features, then train a real candidate model through the already-built (but never yet exercised end-to-end) `ml_training` package and validate it on genuinely held-out, never-seen data.

**Architecture:** A small refactor extracts the live Technical engine's feature computation into a pure, reusable function; a new backfill script calls it against historical OHLCV windows and writes directly to the offline Feature Store with honestly-backdated timestamps; a new training script then drives `ml_training.service.MLTrainingService.run_training_job` (training) and `ml_training.evaluation.ModelEvaluator` (held-out evaluation) against that now-populated store, injecting a caching price-fetcher to avoid tens of thousands of redundant live network calls during label generation.

**Tech Stack:** Python 3.12, PostgreSQL (`feature_store_records`), yfinance, XGBoost, pytest.

**Spec:** `docs/superpowers/specs/2026-10-01-feature-store-backfill-and-ml-candidate-design.md`

## Global Constraints

- **No SHADOW deployment, no ACTIVE promotion anywhere in this plan.** Nothing here calls `ml_training/shadow/service.py::deploy_shadow()` or any `ml_training/registry/service.py` promotion method. The candidate stays at `CANDIDATE`.
- **Backfilled rows' `ingestion_timestamp` must equal the historical date being backfilled, never "now".** This is the one property that makes `respect_ingestion_time=True` training queries correct. `FeatureStoreService.write_feature()` hardcodes `ingestion_timestamp=datetime.now(timezone.utc)` and CANNOT be used for backfill — the backfill writes directly via `PostgresOfflineStore.insert()`, which accepts a caller-supplied `ingestion_timestamp`. This is a deliberate, necessary exception to the module's own "never construct the stores directly" guidance, not an oversight.
- **The backfill must reuse the live Technical engine's exact feature computation** (the extracted `compute_technical_features` function), not a reimplementation.
- **Idempotent/resumable backfill** — re-running it after a partial failure must not duplicate rows or redo completed work.
- `horizon_days=5`, label `direction_band_pct=1.0%` (the `MLTrainingConfig` default) — matches PR #3's `xgb_signal_model_oos_test` exactly, for a fair comparison.
- Report results honestly, including an unfavorable outcome (the candidate may not beat baseline — that's a legitimate finding, not something to tune away).
- Every commit ends with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Continue in the existing worktree (`/home/mayasoft/app/OptiTrade/.claude/worktrees/ml-oos-retrain`, branch `worktree-ml-oos-retrain`) — already set up, already has `backend/.env`, already has PR #3's commits. No new worktree.

---

### Task 1: Extract `compute_technical_features` from `_compute_all`

**Files:**
- Modify: `backend/src/engines/technical/feature_adapter.py:108-188` (`_compute_all`)
- Test: `backend/src/tests/test_technical_engine_feature_adapter.py` (existing — run before and after, must pass identically)

**Interfaces:**
- Produces: `compute_technical_features(hist: pd.DataFrame, config: TechnicalEngineConfig) -> Dict[str, float]` — a new, pure, module-level function in `engines/technical/feature_adapter.py`. Consumed by Task 2's backfill script.

- [ ] **Step 1: Read the current `_compute_all` in full**

Already read during planning — lines 108-188 of `backend/src/engines/technical/feature_adapter.py`. It does three things in sequence: (a) `fetch_history(symbol, period=self.config.price_period)` — the ONLY live-coupled part; (b) compute all 17 `ALL_FEATURE_NAMES` values from the resulting `hist` DataFrame; (c) write each value to `self.feature_store`. This task splits (b) out into its own pure function.

- [ ] **Step 2: Run the existing test suite to capture the baseline**

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_technical_engine_feature_adapter.py -v`
Record the exact pass/fail output — this is the baseline Step 4 must match exactly.

- [ ] **Step 3: Extract the pure computation into `compute_technical_features`**

In `backend/src/engines/technical/feature_adapter.py`, add this new module-level function (place it right after the imports, before the `TechnicalFeatureAdapter` class):

```python
def compute_technical_features(hist: "pd.DataFrame", config: TechnicalEngineConfig) -> Dict[str, float]:
    """Pure computation of all `ALL_FEATURE_NAMES` values from an
    already-fetched OHLCV `hist` DataFrame - no Feature Store, no
    network I/O, no side effects. Extracted from `TechnicalFeatureAdapter
    ._compute_all` (which still does the live fetch-and-write around a
    call to this function) so the exact same feature definitions can be
    reused against a HISTORICAL `hist` window by
    `scripts/backfill_feature_store.py` - the live engine and the
    backfill must compute "RSI" (and everything else) identically, or a
    model trained on backfilled history would see a different feature
    distribution than it sees at live-vote time later."""
    if hist is None or hist.empty:
        return {}

    prices = hist["Close"]
    high, low, close, volume = hist["High"], hist["Low"], hist["Close"], hist["Volume"]
    current_price = float(prices.iloc[-1])

    values: Dict[str, float] = {}

    trend_strength = calculate_trend_strength(prices)
    if trend_strength is not None:
        values[FEATURE_TREND_STRENGTH] = trend_strength

    ema_crossover = calculate_ema_crossover(prices)
    values[FEATURE_EMA_CROSSOVER] = EMA_CROSSOVER_ENCODING.get(ema_crossover, 0.0)

    macd_line, macd_signal, macd_hist = calculate_macd(prices)
    if macd_line is not None:
        values[FEATURE_MACD_LINE] = macd_line
        values[FEATURE_MACD_SIGNAL] = macd_signal
        values[FEATURE_MACD_HISTOGRAM] = macd_hist

    roc = calculate_roc(prices)
    if roc is not None:
        values[FEATURE_ROC] = roc

    rsi = calculate_rsi(prices)
    if rsi is not None:
        values[FEATURE_RSI] = rsi

    bollinger = calculate_bollinger_bands(prices)
    if bollinger.get("percent_b") is not None:
        values[FEATURE_BB_PERCENT_B] = bollinger["percent_b"]
    if bollinger.get("bandwidth") is not None:
        values[FEATURE_BB_BANDWIDTH] = bollinger["bandwidth"]

    atr_series = ta.atr(high, low, close, length=14)
    if atr_series is not None and not atr_series.empty and not bool(np.isnan(atr_series.iloc[-1])):
        atr_value = float(atr_series.iloc[-1])
        values[FEATURE_ATR] = atr_value
        if current_price > 0:
            values[FEATURE_ATR_PCT] = atr_value / current_price * 100

    current_volume = float(volume.iloc[-1])
    avg_volume = float(volume.tail(config.volume_average_window).mean())
    values[FEATURE_VOLUME_RATIO] = calculate_volume_ratio(current_volume, avg_volume)

    vwap = calculate_vwap(high, low, close, volume)
    if vwap is not None and vwap > 0:
        values[FEATURE_VWAP_DIFF] = (current_price - vwap) / vwap * 100

    scanner = PatternScanner(
        support_resistance_lookback_days=config.support_resistance_lookback_days
    )
    scan = scanner.scan(daily_df=hist, hourly_df=None)
    if scan.get("support_proximity_pct") is not None:
        values[FEATURE_SUPPORT_PROXIMITY] = scan["support_proximity_pct"]
    if scan.get("resistance_proximity_pct") is not None:
        values[FEATURE_RESISTANCE_PROXIMITY] = scan["resistance_proximity_pct"]

    active_patterns = scan.get("active_patterns", [])
    values[FEATURE_BULLISH_PATTERN_COUNT] = float(
        sum(1 for p in active_patterns if any(p.startswith(bp) for bp in BULLISH_PATTERNS))
    )
    values[FEATURE_BEARISH_PATTERN_COUNT] = float(
        sum(1 for p in active_patterns if any(p.startswith(bp) for bp in BEARISH_PATTERNS))
    )

    return values
```

Then replace `_compute_all`'s body (keep the method, keep its signature) with:

```python
    def _compute_all(self, symbol: str) -> Dict[str, float]:
        started_at = time.perf_counter()
        hist = fetch_history(symbol, period=self.config.price_period)
        values = compute_technical_features(hist, self.config)

        for name, value in values.items():
            self.feature_store.write_feature(FeatureValue(symbol=symbol, feature_name=name, value=value))

        log_event(
            logger, component="technical_engine", module="engines.technical.feature_adapter",
            operation="compute_all", status=STATUS_SUCCESS, symbol=symbol,
            features_computed=len(values),
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return values
```

This needs `import pandas as pd` added at the top of the file if not already present (check — the file currently only imports `numpy as np`, `pandas_ta as ta`; it does NOT import `pandas` directly, since `hist` was always a parameter passed around, never type-annotated against the real `pd.DataFrame` type before). Add `import pandas as pd` to the imports block, and use `pd.DataFrame` (not the quoted-string `"pd.DataFrame"`) in `compute_technical_features`'s signature once the import is present.

- [ ] **Step 4: Run the test suite again to confirm zero behavior change**

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_technical_engine_feature_adapter.py -v`
Expected: identical pass/fail result to Step 2's baseline — same tests pass, same count, nothing newly broken. If anything differs, the extraction introduced a behavior change and must be fixed before proceeding (compare the old and new `_compute_all` bodies line-by-line against this plan's Step 3 code to find the discrepancy).

- [ ] **Step 5: Run the broader engine test suite as a sanity check**

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_technical_engine_engine.py src/tests/test_technical_engine_config.py -v`
Expected: all pass (these exercise `TechnicalEngine`/`TechnicalFeatureAdapter` more broadly and would catch an import-time error from the new `compute_technical_features` function or a broken `pd` import).

- [ ] **Step 6: Commit**

```bash
cd backend && git add src/engines/technical/feature_adapter.py
git commit -m "refactor: extract compute_technical_features from _compute_all

Splits TechnicalFeatureAdapter._compute_all into its live-coupled part
(fetch_history + Feature Store writes, unchanged) and a new pure
module-level function, compute_technical_features(hist, config), that
takes any already-fetched OHLCV DataFrame. Zero behavior change for the
live engine - confirmed by the existing test suite passing identically
before and after.

This is a prerequisite for scripts/backfill_feature_store.py (next
commit), which needs to compute the exact same 17 ALL_FEATURE_NAMES
features the live engine computes, but against historical OHLCV
windows instead of a live fetch_history() call - reusing this function
guarantees the backfilled history and future live-computed features
are bit-for-bit consistent in method.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Feature Store backfill script

**Files:**
- Create: `backend/src/scripts/backfill_feature_store.py`
- Test: `backend/src/tests/test_backfill_feature_store.py` (new)

**Interfaces:**
- Consumes: `engines.technical.feature_adapter.compute_technical_features` (Task 1), `feature_store.offline_store.PostgresOfflineStore`, `feature_store.models.FeatureRecord`.
- Produces: historical rows in `feature_store_records` for `SYMBOL_BASKET` over `[BACKFILL_START, BACKFILL_END]`. Consumed by Task 3's training/evaluation run (which reads them via `ml_training.features.extractor.FeatureExtractor`).

- [ ] **Step 1: Write the failing unit test for the idempotency/skip logic**

```python
# backend/src/tests/test_backfill_feature_store.py
"""Unit tests for scripts/backfill_feature_store.py's pure logic (date
iteration, skip-if-exists check) - the actual end-to-end backfill run
against real Postgres/yfinance is exercised manually (Task 2's own
Step 5-7 below), not here, matching this plan's precedent for
scripts/evaluate_model_accuracy.py (no pytest coverage for a one-time,
real-network diagnostic script's main() - only its pure helper logic is
unit-tested)."""
import sys
sys.path.insert(0, ".")

from datetime import datetime, timezone

import pandas as pd

from scripts.backfill_feature_store import (
    _price_period_to_days,
    already_backfilled,
    trading_days_in_range,
)


def test_trading_days_in_range_excludes_weekends():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)   # a Thursday
    end = datetime(2026, 1, 7, tzinfo=timezone.utc)     # the following Wednesday
    days = trading_days_in_range(start, end)
    weekdays = {d.weekday() for d in days}
    assert 5 not in weekdays and 6 not in weekdays  # no Saturday (5) or Sunday (6)
    assert len(days) == 5  # Thu, Fri, Mon, Tue, Wed


def test_already_backfilled_true_when_row_exists(monkeypatch):
    target_day = datetime(2026, 1, 1, tzinfo=timezone.utc)

    class _FakeRecord:
        event_timestamp = target_day

    class _FakeStore:
        def get_as_of(self, symbol, feature_name, as_of, respect_ingestion_time=False):
            return _FakeRecord()

    assert already_backfilled(_FakeStore(), "AAPL", target_day) is True


def test_already_backfilled_false_when_no_row(monkeypatch):
    class _FakeStore:
        def get_as_of(self, symbol, feature_name, as_of, respect_ingestion_time=False):
            return None

    assert already_backfilled(_FakeStore(), "AAPL", datetime(2026, 1, 1, tzinfo=timezone.utc)) is False


def test_price_period_to_days_parses_months_years_and_days():
    assert _price_period_to_days("6mo") == 180
    assert _price_period_to_days("1y") == 365
    assert _price_period_to_days("90d") == 90


def test_price_period_to_days_rejects_unrecognized_format():
    import pytest
    with pytest.raises(ValueError):
        _price_period_to_days("bogus")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_backfill_feature_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.backfill_feature_store'`

- [ ] **Step 3: Write the backfill script**

```python
# backend/src/scripts/backfill_feature_store.py
"""OptiTrade — Feature Store historical backfill.

Usage (from backend/src):
  python scripts/backfill_feature_store.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]

Backfills ~2 years of historical, point-in-time Technical-engine
features (the same 17 ALL_FEATURE_NAMES the live engine computes, via
engines.technical.feature_adapter.compute_technical_features) into the
offline Feature Store, so ml_training's point-in-time dataset builder
has enough history to train on - the Feature Store was found to have
only ~2 months of real history (2026-07-29 onward), far short of what a
meaningful training window needs.

Writes DIRECTLY via PostgresOfflineStore.insert(), bypassing
FeatureStoreService.write_feature() - that facade hardcodes
ingestion_timestamp=datetime.now(), which would defeat the entire point
of this backfill (every row would look like it was "just ingested",
making DatasetBuilder's respect_ingestion_time=True queries treat none
of this history as having been known at the time it claims to be from).
This script instead sets BOTH event_timestamp and ingestion_timestamp
to the historical day being backfilled - an honest backdate, not a
workaround, and exactly what the schema's own caller-supplied
ingestion_timestamp field exists to support.

Idempotent: for each (symbol, day), checks whether a row already exists
before computing/writing - a killed/restarted run skips already-done
work rather than duplicating it.
"""
from __future__ import annotations

import argparse
import sys
sys.path.insert(0, ".")

import logging
from datetime import datetime, timedelta, timezone
from typing import List

import yfinance as yf

from engines.technical.config import TechnicalEngineConfig
from engines.technical.feature_adapter import compute_technical_features
from feature_store.models import FeatureRecord
from feature_store.offline_store import PostgresOfflineStore
from research.ml_trainer import SYMBOLS

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def trading_days_in_range(start: datetime, end: datetime) -> List[datetime]:
    """Every calendar day in [start, end] that isn't a Saturday/Sunday -
    a cheap proxy for "is this likely a trading day" that doesn't need a
    market-calendar dependency. Weekday OHLCV will simply be absent from
    yfinance's returned history for actual market holidays, which the
    per-day lookup below already handles by finding no matching row."""
    days = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:  # Monday=0 .. Friday=4
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def already_backfilled(store: PostgresOfflineStore, symbol: str, day: datetime) -> bool:
    """True if ANY feature is already recorded for (symbol, day) - used
    as the per-day skip check. Checks a single representative feature
    (trend_strength_pct) rather than all 17, since this script always
    writes all 17 together for a given day - if one is present, the
    whole day's backfill already ran for this symbol."""
    from engines.technical.config import FEATURE_TREND_STRENGTH

    record = store.get_as_of(symbol, FEATURE_TREND_STRENGTH, day, respect_ingestion_time=False)
    return record is not None and record.event_timestamp.date() == day.date()


def _price_period_to_days(price_period: str) -> int:
    """Converts a yfinance-style period string ("6mo", "1y", "90d") to
    an approximate calendar-day count - used to bound each backfilled
    day's feature-computation window to the SAME trailing length the
    live engine's own `fetch_history(symbol, period=config.price_period)`
    would use. This matters: trend_strength (a linear regression over
    the window) and other indicators are NOT invariant to window length,
    so feeding compute_technical_features a differently-sized window
    than the live engine uses would silently violate this backfill's
    core "bit-for-bit consistent in method" guarantee, even while reusing
    the exact same function."""
    unit = price_period[-2:] if price_period.endswith("mo") else price_period[-1:]
    amount = int(price_period[:-len(unit)])
    if unit == "d":
        return amount
    if unit == "mo":
        return amount * 30
    if unit == "y":
        return amount * 365
    raise ValueError(f"unrecognized price_period format: {price_period!r}")


def backfill_symbol(store: PostgresOfflineStore, config: TechnicalEngineConfig, symbol: str, start: datetime, end: datetime) -> int:
    """Fetches `symbol`'s full historical OHLCV ONCE (not once per day),
    then computes and writes features for every trading day in
    [start, end] not already backfilled. Returns the number of days
    actually written (skipped days don't count)."""
    window_days = _price_period_to_days(config.price_period)
    fetch_start = (start - timedelta(days=window_days + 10)).strftime("%Y-%m-%d")
    fetch_end = (end + timedelta(days=1)).strftime("%Y-%m-%d")
    hist = yf.Ticker(symbol).history(start=fetch_start, end=fetch_end)
    if hist is None or hist.empty:
        logger.warning("%s: no history returned, skipping entirely", symbol)
        return 0

    written = 0
    for day in trading_days_in_range(start, end):
        if already_backfilled(store, symbol, day):
            continue

        # Trailing window of the SAME length the live engine's
        # fetch_history(symbol, period=config.price_period) call would
        # return if it ran live on `day` - not "all history up to day",
        # which would make indicators like trend_strength compute
        # differently than the live engine does for the same date.
        window_start_date = (day - timedelta(days=window_days)).date()
        window = hist[(hist.index.date > window_start_date) & (hist.index.date <= day.date())]
        if len(window) < window_days // 4:  # not enough prior history yet for this early a day
            continue

        values = compute_technical_features(window, config)
        if not values:
            continue

        day_end_utc = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=timezone.utc)
        for feature_name, value in values.items():
            store.insert(FeatureRecord(
                symbol=symbol, feature_name=feature_name, value=value, version="v1",
                event_timestamp=day_end_utc, ingestion_timestamp=day_end_utc,
            ))
        written += 1
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=str, default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--end", type=str, default=None, metavar="YYYY-MM-DD")
    args = parser.parse_args()

    end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc) if args.end else datetime.now(timezone.utc)
    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc) if args.start else end - timedelta(days=730)

    print("=" * 65)
    print("OptiTrade - Feature Store Backfill")
    print(f"Range: {start.date().isoformat()} .. {end.date().isoformat()} | Symbols: {len(SYMBOLS)}")
    print("=" * 65)

    store = PostgresOfflineStore()
    config = TechnicalEngineConfig.from_env()

    total_written = 0
    for symbol in SYMBOLS:
        print(f"  Backfilling: {symbol}...", end=" ", flush=True)
        written = backfill_symbol(store, config, symbol, start, end)
        total_written += written
        print(f"{written} days written")

    print(f"\nToplam: {total_written} sembol-gün yazıldı.")
    print("=" * 65)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the unit test to verify it passes**

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_backfill_feature_store.py -v`
Expected: 5 passed

- [ ] **Step 5: Run the backfill for real, in the background, with visible progress**

This is a real, multi-minute (estimated 10-30 minutes per the spec's Risks section, could run longer) job against real Postgres and real yfinance data for 22 symbols over ~2 years. Run it as a background process so progress is visible without blocking:

```bash
cd backend/src && ~/app/OptiTrade/venv/bin/python3 scripts/backfill_feature_store.py --start 2024-10-01 --end 2026-10-01 > /tmp/backfill_run.log 2>&1 &
```

Poll `/tmp/backfill_run.log` periodically (e.g. `tail -20 /tmp/backfill_run.log`) rather than waiting silently. If it is still running after 45 minutes with per-symbol progress lines appearing at a reasonable pace (not stalled on one symbol), let it continue - this is expected, not a sign of a problem. If a single symbol's line never completes after several minutes (stalled, not just slow), investigate that specific symbol (likely a yfinance rate-limit or a delisted/renamed ticker) rather than killing the whole run.

- [ ] **Step 6: Verify the backfill actually ran and the dates are honest**

Once complete, run this verification query directly - this is the single most important check in this task, per the spec's own Risks section (a bug leaving `ingestion_timestamp` at "now" would silently defeat the whole point of this backfill while looking identical in row counts):

```bash
cd backend/src && ~/app/OptiTrade/venv/bin/python3 -c "
from feature_store.offline_store import PostgresOfflineStore
from datetime import datetime, timezone
store = PostgresOfflineStore()
conn = store._pool.getconn()
try:
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*), MIN(event_timestamp), MAX(event_timestamp), COUNT(DISTINCT symbol) FROM feature_store_records')
        print('overall:', cur.fetchone())
        # The critical check: pick one backfilled row and confirm its
        # ingestion_timestamp is the HISTORICAL date, not today.
        cur.execute(\"\"\"
            SELECT symbol, feature_name, event_timestamp, ingestion_timestamp
            FROM feature_store_records
            WHERE event_timestamp < %s
            ORDER BY event_timestamp ASC LIMIT 1
        \"\"\", (datetime(2026, 7, 1, tzinfo=timezone.utc),))
        row = cur.fetchone()
        print('earliest backfilled row:', row)
        assert row is not None, 'backfill produced no rows before the pre-existing ~2026-07-29 data - did it run?'
        event_ts, ingestion_ts = row[2], row[3]
        assert event_ts == ingestion_ts, f'ingestion_timestamp ({ingestion_ts}) must equal event_timestamp ({event_ts}) for a backfilled row - got a mismatch, meaning ingestion_timestamp defaulted to something other than the intended historical date'
        assert ingestion_ts.date() < datetime(2026, 9, 1, tzinfo=timezone.utc).date(), f'ingestion_timestamp {ingestion_ts} is suspiciously recent for a backfilled row - check it is not actually \"now\"'
        print('VERIFIED: backfilled row has an honest, historical ingestion_timestamp.')
finally:
    store._pool.putconn(conn)
"
```

Expected: prints the overall row count (should now be well over 100,000, up from the pre-backfill 20,453), prints the earliest backfilled row, and both `assert` statements pass without raising.

- [ ] **Step 7: Commit**

```bash
cd backend && git add src/scripts/backfill_feature_store.py src/tests/test_backfill_feature_store.py
git commit -m "feat: add Feature Store historical backfill script

Backfills ~2 years of point-in-time Technical-engine features (reusing
compute_technical_features from the previous commit) into
feature_store_records, writing directly via PostgresOfflineStore.insert()
with BOTH event_timestamp and ingestion_timestamp honestly backdated to
the historical day - FeatureStoreService.write_feature() cannot do this
(it hardcodes ingestion_timestamp=now()), which would defeat
DatasetBuilder's respect_ingestion_time=True leakage guard entirely.

Idempotent (skips already-backfilled symbol/day pairs) and fetches each
symbol's full OHLCV history once rather than once per day. Run for real
against the 22-symbol BIST+crypto basket, [2024-10-01, 2026-10-01]:
<FILL IN ACTUAL total_written COUNT AND overall row count FROM STEP 6's
real output HERE - do not write a placeholder, the implementer running
this step has the real numbers>.

Verified: queried a backfilled row directly and confirmed
ingestion_timestamp honestly equals the historical event_timestamp, not
today's date - the critical property this backfill exists to establish.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

(The implementer MUST replace the bracketed placeholder with the actual numbers Step 6 produced before committing — this is the one exception to writing the commit message in advance, because the real counts don't exist until the real backfill has run.)

---

### Task 3: Train and evaluate a real candidate via `ml_training`

**Files:**
- Create: `backend/src/scripts/train_ml_candidate.py`
- Create: `docs/ml-candidate-report-2026-10-01.md` (output of running the script)

**Interfaces:**
- Consumes: the backfilled Feature Store (Task 2), `ml_training.service.MLTrainingService`, `ml_training.datasets.builder.DatasetBuilder`, `ml_training.evaluation.evaluator.ModelEvaluator`, `ml_training.labels.generator.PriceFetcher` (the `Callable[[str, datetime, datetime], Optional[pd.DataFrame]]` protocol).
- Produces: one registered `CANDIDATE` model in `ml_training`'s registry, plus an honest out-of-sample evaluation report.

- [ ] **Step 1: Write the failing unit test for the caching price-fetcher**

```python
# backend/src/tests/test_train_ml_candidate.py
"""Unit test for train_ml_candidate.py's CachingPriceFetcher - the
actual end-to-end training run against the real (now-backfilled)
Feature Store is exercised manually (this task's Step 3-5 below), not
here, matching this plan's Task 2 precedent."""
import sys
sys.path.insert(0, ".")

from datetime import datetime, timezone

import pandas as pd

from scripts.train_ml_candidate import CachingPriceFetcher


def test_caching_price_fetcher_slices_without_refetching(monkeypatch):
    call_count = {"n": 0}

    class _FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, start, end):
            call_count["n"] += 1
            idx = pd.date_range("2026-01-01", periods=10, freq="D", tz="UTC")
            return pd.DataFrame({"Close": range(10)}, index=idx)

    import scripts.train_ml_candidate as mod
    monkeypatch.setattr(mod.yf, "Ticker", _FakeTicker)

    fetcher = CachingPriceFetcher(["AAPL"], datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 10, tzinfo=timezone.utc))
    assert call_count["n"] == 1  # fetched once at construction, for the one symbol

    first = fetcher("AAPL", datetime(2026, 1, 2, tzinfo=timezone.utc), datetime(2026, 1, 5, tzinfo=timezone.utc))
    second = fetcher("AAPL", datetime(2026, 1, 3, tzinfo=timezone.utc), datetime(2026, 1, 6, tzinfo=timezone.utc))
    assert call_count["n"] == 1  # neither per-call slice triggered a new fetch
    assert first is not None and not first.empty
    assert second is not None and not second.empty


def test_caching_price_fetcher_returns_none_for_unknown_symbol():
    fetcher = CachingPriceFetcher([], datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 10, tzinfo=timezone.utc))
    assert fetcher("NOPE", datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 2, tzinfo=timezone.utc)) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_train_ml_candidate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.train_ml_candidate'`

- [ ] **Step 3: Write the training + evaluation script**

```python
# backend/src/scripts/train_ml_candidate.py
"""OptiTrade — ML candidate training via the ml_training package.

Usage (from backend/src):
  python scripts/train_ml_candidate.py

Prerequisite: scripts/backfill_feature_store.py must already have been
run for the same date range - this script trains from the Feature
Store's point-in-time history, not raw OHLCV.

Trains one XGBoost DIRECTION classifier (horizon_days=5,
dataset_type=TRADER - matching PR #3's xgb_signal_model_oos_test
exactly, for a fair comparison) via ml_training.service
.MLTrainingService.run_training_job on [TRAIN_START, TRAIN_END_DATE],
producing a registered CANDIDATE model. Then builds a SEPARATE held-out
dataset strictly AFTER TRAIN_END_DATE (through TRAIN_END - same
no-overlap discipline PR #3 established) and scores the trained model
against it via ml_training.evaluation.ModelEvaluator - genuine
out-of-sample, not the training run's own in-training CV metrics.

Injects CachingPriceFetcher everywhere ml_training's label generation
needs forward-looking price data (ml_training.labels.generator
.generate_labels calls a PriceFetcher once per (symbol, as_of,
horizon_days) sample - with ~2 years x 22 symbols, that is tens of
thousands of calls; without caching, each would be a live yfinance
network request, making this script take hours rather than minutes).
Does NOT deploy to SHADOW or promote to ACTIVE - the candidate is left
exactly as CANDIDATE, a separate, later, human-approved decision.
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from ml_training.config import MLTrainingConfig
from ml_training.datasets.builder import DatasetBuilder
from ml_training.datasets.service import DatasetService
from ml_training.evaluation.evaluator import ModelEvaluator
from ml_training.features.extractor import FeatureExtractor
from ml_training.models import DatasetType, LabelName, ModelAlgorithm
# _samples_to_arrays is underscore-prefixed (module-private by convention)
# but is reused deliberately here rather than reimplemented: it is the
# exact TrainingSample-list -> (X, y, returns) conversion
# MLTrainingService.run_training_job's own _time_split uses internally,
# and ModelEvaluator.evaluate needs the held-out samples in that same
# array shape. Duplicating this ~4-line function would risk the two
# copies silently drifting (e.g. a future labels.py field rename updated
# in one copy but not the other) - reuse is the DRY choice even across
# the underscore boundary.
from ml_training.service import MLTrainingService, _samples_to_arrays
from ml_training.training.service import create_trainer
from research.ml_trainer import SYMBOLS

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

_AUTHOR = "train_ml_candidate_script"
HORIZON_DAYS = 5  # matches research/ml_trainer.py's FORWARD_DAYS - fair comparison with xgb_signal_model_oos_test


class CachingPriceFetcher:
    """A `ml_training.labels.generator.PriceFetcher`-compatible callable
    that fetches each symbol's full OHLCV history ONCE at construction,
    then serves every subsequent (symbol, start, end) call by slicing
    the pre-fetched DataFrame in memory - avoids tens of thousands of
    redundant live yfinance calls when building a multi-year, multi-
    symbol dataset (one per training sample otherwise)."""

    def __init__(self, symbols: List[str], overall_start: datetime, overall_end: datetime) -> None:
        self._cache: Dict[str, pd.DataFrame] = {}
        fetch_start = (overall_start - timedelta(days=10)).strftime("%Y-%m-%d")
        fetch_end = (overall_end + timedelta(days=10)).strftime("%Y-%m-%d")
        for symbol in symbols:
            try:
                hist = yf.Ticker(symbol).history(start=fetch_start, end=fetch_end)
                if hist is not None and not hist.empty:
                    self._cache[symbol] = hist
            except Exception as exc:
                logger.warning("%s: price cache fetch failed: %s", symbol, exc)

    def __call__(self, symbol: str, start: datetime, end: datetime) -> Optional[pd.DataFrame]:
        hist = self._cache.get(symbol)
        if hist is None or hist.empty:
            return None
        sliced = hist[(hist.index >= start) & (hist.index < end)]
        return sliced if not sliced.empty else None


def main() -> None:
    config = MLTrainingConfig.from_env()
    now = datetime.now(timezone.utc)
    train_end_date = now - timedelta(days=180)  # 6 months before "now" - same convention PR #3 established
    train_start = train_end_date - timedelta(days=730)

    print("=" * 65)
    print("OptiTrade - ML Candidate Training (ml_training package)")
    print(f"Train: [{train_start.date().isoformat()}, {train_end_date.date().isoformat()}] | "
          f"Held-out eval: ({train_end_date.date().isoformat()}, {now.date().isoformat()}]")
    print(f"Symbols: {len(SYMBOLS)} | horizon_days={HORIZON_DAYS} | algorithm=xgboost")
    print("=" * 65)

    price_fetcher = CachingPriceFetcher(SYMBOLS, train_start, now)

    dataset_service = DatasetService(
        builder=DatasetBuilder(feature_extractor=FeatureExtractor(), config=config, price_fetcher=price_fetcher),
        config=config,
    )
    service = MLTrainingService(datasets=dataset_service, config=config)

    print("\nEğitim çalıştırılıyor (bu birkaç dakika sürebilir)...")
    result = service.run_training_job(
        author=_AUTHOR, symbols=SYMBOLS, dataset_type=DatasetType.TRADER,
        label_name=LabelName.DIRECTION, horizon_days=HORIZON_DAYS,
        algorithm=ModelAlgorithm.XGBOOST, start=train_start, end=train_end_date,
    )
    print(f"CANDIDATE kaydedildi: model_id={result.registry_entry.model_id}")
    print(f"In-training CV/test metrikleri: accuracy={result.metrics.accuracy:.3f}")
    print(f"Hipotez sonucu: {result.hypothesis_outcome.value}")

    print("\nGerçek out-of-sample değerlendirme çalıştırılıyor...")
    held_out_builder = DatasetBuilder(feature_extractor=FeatureExtractor(), config=config, price_fetcher=price_fetcher)
    held_out_samples, held_out_version = held_out_builder.build(
        SYMBOLS, DatasetType.TRADER, start=train_end_date, end=now, horizons_days=[HORIZON_DAYS],
    )

    trainer = create_trainer(ModelAlgorithm.XGBOOST, result.training_run.task_type, result.registry_entry.feature_list, config=config)
    trainer.load(result.registry_entry.artifact_path)

    X_oos, y_oos, returns_oos = _samples_to_arrays(held_out_samples, result.registry_entry.feature_list, LabelName.DIRECTION)
    evaluator = ModelEvaluator(config=config)
    oos_metrics = evaluator.evaluate(trainer, X_oos, y_oos, actual_returns=returns_oos)

    unique, counts = pd.Series(y_oos).value_counts().index.tolist(), pd.Series(y_oos).value_counts().tolist()
    majority_baseline = max(counts) / len(y_oos) if len(y_oos) else 0.0

    lines = [
        f"# ML Candidate Report — {now.date().isoformat()}", "",
        f"Model: `{result.registry_entry.model_id}` (algorithm=xgboost, label=direction, horizon_days={HORIZON_DAYS})",
        f"Promotion state: `{result.registry_entry.promotion_state.value}` (CANDIDATE only - no SHADOW/ACTIVE in this run)",
        "", "## Held-out out-of-sample evaluation", "",
        f"Train window: [{train_start.date().isoformat()}, {train_end_date.date().isoformat()}]",
        f"Held-out window (strictly after train_end_date): ({train_end_date.date().isoformat()}, {now.date().isoformat()}]",
        f"Held-out samples: {len(held_out_samples)}", "",
        f"| Metric | Value |", f"|---|---|",
        f"| Accuracy | {oos_metrics.accuracy:.3f} |",
        f"| Majority baseline | {majority_baseline:.3f} |",
        f"| Precision | {oos_metrics.precision:.3f} |",
        f"| Recall | {oos_metrics.recall:.3f} |",
        "", "## In-training metrics (for reference, NOT the out-of-sample result above)", "",
        f"| Metric | Value |", f"|---|---|",
        f"| Accuracy | {result.metrics.accuracy:.3f} |",
        f"| Hypothesis outcome | {result.hypothesis_outcome.value} |",
    ]
    report = "\n".join(lines)
    print("\n" + report)
    with open("../../docs/ml-candidate-report-2026-10-01.md", "w") as f:
        f.write(report + "\n")


if __name__ == "__main__":
    main()
```

(Check `ModelMetrics`' exact field names — e.g. whether it's `accuracy`/`precision`/`recall` or different names — against `backend/src/ml_training/models.py`'s `ModelMetrics` class and `backend/src/ml_training/evaluation/metrics.py`'s `classification_metrics` return keys before running; adjust the f-strings above to match the REAL field names if they differ from what's shown here, which was written from memory of PR #2's work and may not be exact.)

- [ ] **Step 4: Run the unit test to verify it passes**

Run: `cd backend && ~/app/OptiTrade/venv/bin/python3 -m pytest src/tests/test_train_ml_candidate.py -v`
Expected: 2 passed

- [ ] **Step 5: Run the training + evaluation for real, in the background**

Only after Task 2's backfill has completed and been verified. This involves real dataset-building (iterating ~730 days × 22 symbols against the now-backfilled Postgres Feature Store) plus real XGBoost training plus a second held-out dataset build — expect this to take meaningful time (likely similar order of magnitude to the backfill, possibly more given the per-sample Feature Store queries); run it in the background with visible output, not silently:

```bash
cd backend/src && ~/app/OptiTrade/venv/bin/python3 scripts/train_ml_candidate.py > /tmp/train_candidate_run.log 2>&1 &
```

Poll `/tmp/train_candidate_run.log` periodically. If `InsufficientDataError` is raised, the backfill (Task 2) did not produce enough samples in the training window - do not proceed by loosening `min_training_samples` or shrinking the window to force a pass; instead verify Task 2's backfill actually covers `[train_start, train_end_date]` with the verification query from Task 2 Step 6, adapted to this script's actual computed `train_start`/`train_end_date` values (printed at the top of this script's own output).

- [ ] **Step 6: Report the real result honestly**

Read the generated `docs/ml-candidate-report-2026-10-01.md` and the full script output. Whatever the out-of-sample accuracy vs majority baseline turns out to be, report it exactly as computed - per this plan's Global Constraints, an unfavorable result (candidate doesn't beat baseline) is a legitimate, complete outcome for this task, not a reason to retry with different parameters until it looks better.

- [ ] **Step 7: Commit**

```bash
cd backend && git add src/scripts/train_ml_candidate.py src/tests/test_train_ml_candidate.py ../docs/ml-candidate-report-2026-10-01.md
git commit -m "feat: train and evaluate a real ML candidate via ml_training

First real exercise of ml_training.service.MLTrainingService
.run_training_job end-to-end (previously only unit-tested, never run
against real data) - an XGBoost DIRECTION classifier (horizon_days=5,
matching PR #3's xgb_signal_model_oos_test for a fair comparison),
trained on the now-backfilled Feature Store's point-in-time history and
registered as CANDIDATE (no SHADOW deployment, no ACTIVE promotion -
both remain separate, later, human-approved steps per the existing
lifecycle code).

Injects CachingPriceFetcher into DatasetBuilder so ml_training.labels
.generator's per-sample forward price lookups (tens of thousands of
them across ~2 years x 22 symbols) hit each symbol's once-fetched,
in-memory OHLCV history instead of making a live yfinance call per
sample.

Evaluated on a SEPARATE held-out dataset built strictly after the
training cutoff (same no-overlap discipline as PR #3) via
ml_training.evaluation.ModelEvaluator - genuine out-of-sample result:

<FILL IN THE ACTUAL accuracy/majority_baseline NUMBERS FROM THE REAL
RUN'S docs/ml-candidate-report-2026-10-01.md HERE - do not write a
placeholder or an assumed-favorable number>.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

(As with Task 2's commit, the implementer MUST replace the bracketed placeholder with the real numbers from the actual run before committing.)

---

## Explicitly Out of Scope (restated from the spec)

- `SHADOW` deployment (`ml_training/shadow/service.py::deploy_shadow()`) and `ACTIVE` promotion — separate, later, human-approved steps.
- Fundamental/News engine feature backfill — Technical engine's 17 features only.
- Hyperparameter optimization (`run_training_job`'s `optimize_hyperparameters`/`n_trials` Optuna path exists but isn't used).
- Retraining/improving the legacy `xgb_signal_model.joblib` (declined in favor of this path).
- The pre-existing `v2_xgb_model` unscoreable-schema issue — unrelated, untouched.
