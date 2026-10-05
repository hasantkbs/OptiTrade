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
dataset strictly AFTER TRAIN_END_DATE (through "now" - same
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
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from engines.technical.config import FEATURE_TREND_STRENGTH
from feature_store.service import get_default_feature_store_service
from ml_training.config import MLTrainingConfig
from ml_training.datasets.builder import DatasetBuilder
from ml_training.datasets.service import DatasetService
from ml_training.evaluation.evaluator import ModelEvaluator
from ml_training.features.derived_builder import DerivedFeatureBuilder
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
REPORT_FILENAME_SUFFIX = os.getenv("TRAIN_ML_CANDIDATE_REPORT_SUFFIX", "")


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


def _earliest_feature_date(symbols: List[str]) -> Optional[datetime]:
    """Earliest `event_timestamp` found across the WHOLE basket, probed
    via FEATURE_TREND_STRENGTH (present for every symbol this plan's
    backfill covers) - used only to warn if real Feature Store coverage
    starts LATER than this script's own computed `train_start`.
    Deliberately queries the real data rather than hardcoding an assumed
    backfill start date, which could silently drift out of sync with
    whatever range `scripts/backfill_feature_store.py` was actually last
    run with. `DatasetBuilder.build` silently `continue`s past days with
    no feature data (see its per-day loop) - it never errors or warns -
    so a training window that nominally starts before real coverage
    begins would otherwise go completely unnoticed, exactly as it did
    for this plan's own first run (see docs/ml-candidate-report-2026-10
    -01.md's fix note)."""
    store = get_default_feature_store_service().offline_store
    very_early = datetime(1970, 1, 1, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    earliest: Optional[datetime] = None
    for symbol in symbols:
        try:
            history = store.get_history(symbol, FEATURE_TREND_STRENGTH, very_early, now)
        except Exception as exc:
            logger.warning("%s: could not determine earliest feature coverage: %s", symbol, exc)
            continue
        if history:  # get_history returns oldest-first
            symbol_earliest = history[0].event_timestamp
            if earliest is None or symbol_earliest < earliest:
                earliest = symbol_earliest
    return earliest


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

    earliest_available = _earliest_feature_date(SYMBOLS)
    if earliest_available is not None and earliest_available.date() > train_start.date():
        logger.warning(
            "Feature Store coverage for this basket starts at %s, AFTER "
            "this script's own computed train_start %s - the EFFECTIVE "
            "training window is narrower than [%s, %s] states. "
            "DatasetBuilder silently skips days with no feature data "
            "rather than erroring, so this would otherwise go unnoticed. "
            "Correct the reported train window accordingly, or re-run "
            "scripts/backfill_feature_store.py with an earlier --start.",
            earliest_available.date().isoformat(), train_start.date().isoformat(),
            train_start.date().isoformat(), train_end_date.date().isoformat(),
        )
        print(
            f"UYARI: Feature Store coverage starts {earliest_available.date().isoformat()}, "
            f"after the computed train_start {train_start.date().isoformat()} - "
            f"see the warning log; the real training window is narrower than nominally computed."
        )

    price_fetcher = CachingPriceFetcher(SYMBOLS, train_start, now)

    dataset_service = DatasetService(
        builder=DatasetBuilder(
            feature_extractor=FeatureExtractor(), config=config, price_fetcher=price_fetcher,
            derived_feature_builder=DerivedFeatureBuilder(price_fetcher=price_fetcher),
        ),
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
    # DatasetBuilder.build's own cursor loop (`while cursor <= end`) is
    # inclusive on BOTH ends, so starting the held-out build at
    # train_end_date itself would re-include that exact calendar day's
    # samples (already used as the training window's inclusive upper
    # bound) in the "held-out" set too - a real train/held-out overlap,
    # not just a cosmetic off-by-one. +1 day makes the held-out window
    # genuinely, not just nominally, strictly after the training cutoff.
    held_out_start = train_end_date + timedelta(days=1)
    held_out_builder = DatasetBuilder(
        feature_extractor=FeatureExtractor(), config=config, price_fetcher=price_fetcher,
        derived_feature_builder=DerivedFeatureBuilder(price_fetcher=price_fetcher),
    )
    held_out_samples, held_out_version = held_out_builder.build(
        SYMBOLS, DatasetType.TRADER, start=held_out_start, end=now, horizons_days=[HORIZON_DAYS],
    )

    trainer = create_trainer(ModelAlgorithm.XGBOOST, result.training_run.task_type, result.registry_entry.feature_list, config=config)
    trainer.load(result.registry_entry.artifact_path)

    X_oos, y_oos, returns_oos = _samples_to_arrays(held_out_samples, result.registry_entry.feature_list, LabelName.DIRECTION)
    evaluator = ModelEvaluator(config=config)
    oos_metrics = evaluator.evaluate(trainer, X_oos, y_oos, actual_returns=returns_oos)

    counts = pd.Series(y_oos).value_counts().tolist()
    majority_baseline = max(counts) / len(y_oos) if len(y_oos) else 0.0

    lines = [
        f"# ML Candidate Report — {now.date().isoformat()}", "",
        f"Model: `{result.registry_entry.model_id}` (algorithm=xgboost, label=direction, horizon_days={HORIZON_DAYS})",
        f"Promotion state: `{result.registry_entry.promotion_state.value}` (CANDIDATE only - no SHADOW/ACTIVE in this run)",
        "", "## Held-out out-of-sample evaluation", "",
        f"Train window: [{train_start.date().isoformat()}, {train_end_date.date().isoformat()}]",
        f"Held-out window (strictly after train_end_date): [{held_out_start.date().isoformat()}, {now.date().isoformat()}]",
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
    report_path = f"../../docs/ml-candidate-report-{now.date().isoformat()}{REPORT_FILENAME_SUFFIX}.md"
    with open(report_path, "w") as f:
        f.write(report + "\n")


if __name__ == "__main__":
    main()
