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
