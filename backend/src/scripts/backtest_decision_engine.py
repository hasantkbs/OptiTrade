"""OptiTrade — decision_engine point-in-time backtest (Technical-only).

Usage (from backend/src):
  python scripts/backtest_decision_engine.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]

Measures decision_engine's own historical decision quality for the
FIRST TIME - using ONLY the Technical voting engine, replayed via
decide(symbol, as_of=historical_day) against the already-backfilled
Feature Store (see docs/superpowers/specs/2026-10-03-decision-engine-
backtest-design.md). This is NOT the full 3-engine live decision:
Fundamental and News cannot be backfilled with current data sources
(yfinance .info/news have no historical query capability) and are
deliberately excluded from this backtest's own engine registry.

Reuses the real decide()/TechnicalEngine code for the replay - this
script supplies as_of and interprets the real DecisionOutput it gets
back, never reimplementing voting/aggregation logic itself.

Direction-labeling matches research/ml_trainer.py's own convention
(FORWARD_DAYS, THRESHOLD_UP) for direct comparability with this
project's existing ML accuracy reports.
"""
from __future__ import annotations

import argparse
import logging
import sys
sys.path.insert(0, ".")

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf

from decision_engine.models import DecisionOutput, Prediction
from decision_engine.registry import VotingEngineRegistry
from decision_engine.service import DecisionEngine
from engines.technical.engine import TechnicalEngine
from providers.binance_provider import BinanceProvider
from research.ml_trainer import FORWARD_DAYS, SYMBOLS, THRESHOLD_UP
from scripts.backfill_feature_store import trading_days_in_range

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


def _fetch_symbol_history(symbol: str, start: datetime, end: datetime) -> Optional[pd.DataFrame]:
    """Real historical closing prices for computing realized forward
    returns - NOT stored in the Feature Store (which only holds derived
    indicator values). Reuses the exact crypto/equity routing
    scripts/backfill_feature_store.py already established: Binance's
    date-bounded range fetch for -USD symbols (yfinance's period-only
    interface can't express this range), yfinance directly otherwise."""
    if symbol.upper().endswith("-USD"):
        hist = BinanceProvider().fetch_ohlcv_range(symbol, start, end)
        if hist is not None and not hist.empty:
            return hist
        logger.warning("%s: Binance range fetch failed, falling back to yfinance", symbol)
    try:
        return yf.Ticker(symbol).history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
    except Exception as exc:
        logger.warning("%s: yfinance fetch failed: %s", symbol, exc)
        return None


def evaluate_decisions(decisions: List[Tuple[DecisionOutput, bool]]) -> dict:
    """Pure evaluation: given (DecisionOutput, actual_was_up) pairs,
    computes accuracy/precision/recall against a naive majority-class
    baseline - EXCLUDING HOLD decisions from the directional count
    (HOLD is an abstention, not a directional prediction; scoring it as
    a miss would corrupt the accuracy number for a system that is
    supposed to be rewarded for correctly declining to call an
    ambiguous day, not punished for it)."""
    directional = [(o, actual) for o, actual in decisions if o.decision != Prediction.HOLD]
    n_hold = len(decisions) - len(directional)

    if not directional:
        return {
            "n_samples": len(decisions), "n_directional_samples": 0, "n_hold": n_hold,
            "accuracy": 0.0, "majority_baseline": 0.0, "precision": 0.0, "recall": 0.0,
        }

    y_true = [1 if actual else 0 for _, actual in directional]
    y_pred = [1 if o.decision == Prediction.BUY else 0 for o, _ in directional]

    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    accuracy = correct / len(directional)
    up_fraction = sum(y_true) / len(y_true)
    majority_baseline = max(up_fraction, 1 - up_fraction)

    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    return {
        "n_samples": len(decisions), "n_directional_samples": len(directional), "n_hold": n_hold,
        "accuracy": accuracy, "majority_baseline": majority_baseline,
        "precision": precision, "recall": recall,
    }


def backtest_symbol(engine: DecisionEngine, symbol: str, days: List[datetime]) -> List[Tuple[DecisionOutput, bool]]:
    """Fetches `symbol`'s real history once, then for each day in `days`
    replays decide(symbol, as_of=day_end_utc) and pairs it with the
    REALIZED direction from day to day+FORWARD_DAYS."""
    fetch_start = days[0] - timedelta(days=5)
    fetch_end = days[-1] + timedelta(days=FORWARD_DAYS + 5)
    hist = _fetch_symbol_history(symbol, fetch_start, fetch_end)
    if hist is None or hist.empty:
        logger.warning("%s: no history available, skipping entirely", symbol)
        return []

    results: List[Tuple[DecisionOutput, bool]] = []
    for day in days:
        day_end_utc = datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=timezone.utc)
        try:
            future_rows = hist[hist.index.date > day.date()]
            if len(future_rows) < FORWARD_DAYS:
                continue  # not enough real future data yet to score this day
            current_rows = hist[hist.index.date <= day.date()]
            if current_rows.empty:
                continue
            current_price = float(current_rows["Close"].iloc[-1])
            future_price = float(future_rows["Close"].iloc[FORWARD_DAYS - 1])
            actual_up = ((future_price - current_price) / current_price) * 100 > THRESHOLD_UP

            output = engine.decide(symbol, as_of=day_end_utc)
            results.append((output, actual_up))
        except Exception as exc:
            logger.warning("%s: failed to backtest %s (%s: %s), skipping this day", symbol, day.date(), type(exc).__name__, exc)
            continue
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", type=str, default=None, metavar="YYYY-MM-DD")
    parser.add_argument("--end", type=str, default=None, metavar="YYYY-MM-DD")
    args = parser.parse_args()

    end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc) if args.end else datetime.now(timezone.utc)
    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc) if args.start else end - timedelta(days=730)

    registry = VotingEngineRegistry()
    registry.register(TechnicalEngine())
    engine = DecisionEngine(registry=registry)

    print("=" * 70)
    print("OptiTrade - decision_engine Point-in-Time Backtest (Technical-only)")
    print(f"Range: {start.date().isoformat()} .. {end.date().isoformat()} | Symbols: {len(SYMBOLS)}")
    print("NOTE: this measures ONLY the Technical voting engine's historical")
    print("decisions - NOT the full 3-engine live decision (Fundamental/News")
    print("cannot be backfilled with current data sources - see the design spec).")
    print("=" * 70)

    all_results: List[Tuple[DecisionOutput, bool]] = []
    per_symbol_counts: Dict[str, int] = {}
    for symbol in SYMBOLS:
        days = trading_days_in_range(start, end, include_weekends=symbol.upper().endswith("-USD"))
        print(f"  Backtesting: {symbol}...", end=" ", flush=True)
        try:
            results = backtest_symbol(engine, symbol, days)
        except Exception as exc:
            logger.warning("%s: backtest_symbol raised %s: %s, skipping entirely", symbol, type(exc).__name__, exc)
            results = []
        per_symbol_counts[symbol] = len(results)
        all_results.extend(results)
        print(f"{len(results)} days evaluated")

    evaluation = evaluate_decisions(all_results)

    lines = [
        f"# decision_engine Point-in-Time Backtest — {datetime.now(timezone.utc).date().isoformat()}", "",
        "**Technical voting engine ONLY — NOT the full 3-engine live decision.**",
        "Fundamental and News engines cannot be backfilled with current data",
        "sources (see docs/superpowers/specs/2026-10-03-decision-engine-backtest-design.md) and are excluded from this backtest's own engine registry entirely.",
        "", "## Result", "",
        "| Samples | Directional samples | HOLD (abstentions) | Accuracy | Majority baseline | Precision | Recall |",
        "|---|---|---|---|---|---|---|",
        f"| {evaluation['n_samples']} | {evaluation['n_directional_samples']} | {evaluation['n_hold']} | "
        f"{evaluation['accuracy']:.3f} | {evaluation['majority_baseline']:.3f} | "
        f"{evaluation['precision']:.3f} | {evaluation['recall']:.3f} |",
        "", f"Per-symbol sample counts: {per_symbol_counts}",
    ]
    report = "\n".join(lines)
    print(report)
    with open(f"../../docs/decision-engine-backtest-report-{datetime.now(timezone.utc).date().isoformat()}.md", "w") as f:
        f.write(report + "\n")


if __name__ == "__main__":
    main()
