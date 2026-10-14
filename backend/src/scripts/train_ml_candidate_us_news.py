"""OptiTrade — ML candidate training, US equities, Technical + SEC
Fundamentals + News (attempt 7 - the last previously-untested feature
family across all 6 prior attempts).

Usage (from backend/src):
  python scripts/train_ml_candidate_us_news.py

Prerequisites: scripts/backfill_feature_store.py --symbols us,
scripts/backfill_sec_fundamentals.py, and
scripts/backfill_news_features.py must already have been run.

Unlike attempt 6 (Technical + SEC Fundamentals), this uses a SHORTER
train/held-out window: News was only backfilled for ~250 trading days
(Finnhub's free tier gives ~1 year of history, vs. SEC Fundamentals'
and Technical's full 2 years) - reusing the same 2-year window as
attempt 6 would train mostly on samples with no real News feature
(defaulted to 0.0, i.e. "neutral"), diluting any chance of detecting
a News effect. This window instead sits entirely inside News'
real backfilled coverage, so every sample has genuine News data, not
a default.
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import logging
import os
from datetime import datetime, timedelta, timezone

import pandas as pd

from core.market_config import US_SYMBOLS
from ml_training.config import MLTrainingConfig
from ml_training.datasets.builder import DatasetBuilder
from ml_training.datasets.service import DatasetService
from ml_training.evaluation.evaluator import ModelEvaluator
from ml_training.features.extractor import FeatureExtractor
from ml_training.models import DatasetType, LabelName, ModelAlgorithm
from ml_training.service import MLTrainingService, _samples_to_arrays
from ml_training.training.service import create_trainer
from scripts.train_ml_candidate import CachingPriceFetcher

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

_AUTHOR = "train_ml_candidate_us_news_script"
HORIZON_DAYS = 5
REPORT_FILENAME_SUFFIX = os.getenv("TRAIN_ML_CANDIDATE_REPORT_SUFFIX", "")
SYMBOLS = list(US_SYMBOLS.keys())

# News' own real backfilled coverage (see module docstring) - the
# train/held-out split below sits entirely inside this, with horizon_
# days of margin at the end so every training sample's forward-looking
# label still has real price history to resolve against.
_NEWS_COVERAGE_START = datetime(2025, 10, 29, tzinfo=timezone.utc)


def main() -> None:
    config = MLTrainingConfig.from_env()
    now = datetime.now(timezone.utc)
    train_start = _NEWS_COVERAGE_START
    held_out_start = now - timedelta(days=90)
    train_end_date = held_out_start - timedelta(days=1)

    print("=" * 65)
    print("OptiTrade - ML Candidate Training (US equities, Technical + SEC Fundamentals + News)")
    print(f"Train: [{train_start.date().isoformat()}, {train_end_date.date().isoformat()}] | "
          f"Held-out eval: [{held_out_start.date().isoformat()}, {now.date().isoformat()}]")
    print(f"Symbols: {len(SYMBOLS)} | horizon_days={HORIZON_DAYS} | algorithm=xgboost | label=direction")
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
    feature_names = result.registry_entry.feature_list
    sec_features = sorted(n for n in feature_names if n.startswith("sec_"))
    news_features = sorted(n for n in feature_names if n.startswith("news_"))
    technical_features = sorted(n for n in feature_names if n not in sec_features and n not in news_features)
    print(f"CANDIDATE kaydedildi: model_id={result.registry_entry.model_id}")
    print(
        f"Toplam özellik: {len(feature_names)} "
        f"({len(technical_features)} Technical, {len(sec_features)} SEC Fundamental, {len(news_features)} News)"
    )
    print(f"In-training accuracy: {result.metrics.accuracy:.3f}")
    print(f"Hipotez sonucu: {result.hypothesis_outcome.value}")

    print("\nGerçek out-of-sample değerlendirme çalıştırılıyor...")
    held_out_builder = DatasetBuilder(feature_extractor=FeatureExtractor(), config=config, price_fetcher=price_fetcher)
    held_out_samples, held_out_version = held_out_builder.build(
        SYMBOLS, DatasetType.TRADER, start=held_out_start, end=now, horizons_days=[HORIZON_DAYS],
    )

    trainer = create_trainer(ModelAlgorithm.XGBOOST, result.training_run.task_type, feature_names, config=config)
    trainer.load(result.registry_entry.artifact_path)

    X_oos, y_oos, returns_oos = _samples_to_arrays(held_out_samples, feature_names, LabelName.DIRECTION)
    evaluator = ModelEvaluator(config=config)
    oos_metrics = evaluator.evaluate(trainer, X_oos, y_oos, actual_returns=returns_oos)

    counts = pd.Series(y_oos).value_counts().tolist()
    majority_baseline = max(counts) / len(y_oos) if len(y_oos) else 0.0
    news_coverage = sum(1 for s in held_out_samples if any(f in s.features for f in news_features))
    sec_coverage = sum(1 for s in held_out_samples if any(f in s.features for f in sec_features))

    lines = [
        f"# ML Candidate Report — {now.date().isoformat()} (US equities, Technical + SEC Fundamentals + News)", "",
        f"Model: `{result.registry_entry.model_id}` (algorithm=xgboost, label=direction, horizon_days={HORIZON_DAYS})",
        f"Promotion state: `{result.registry_entry.promotion_state.value}` (CANDIDATE only - no SHADOW/ACTIVE in this run)",
        f"Basket: {len(SYMBOLS)} US equities ({', '.join(SYMBOLS)})",
        "",
        "## Held-out out-of-sample evaluation",
        "",
        f"Train window: [{train_start.date().isoformat()}, {train_end_date.date().isoformat()}] "
        "(sized to News' own real backfilled coverage - see module docstring)",
        f"Held-out window: [{held_out_start.date().isoformat()}, {now.date().isoformat()}]",
        f"Held-out samples: {len(held_out_samples)} "
        f"({news_coverage} with real News features, {sec_coverage} with real SEC Fundamental features)",
        f"Total features: {len(feature_names)} "
        f"({len(technical_features)} Technical, {len(sec_features)} SEC Fundamental, {len(news_features)} News)",
        "",
        f"| Metric | Value |", f"|---|---|",
        f"| Accuracy | {oos_metrics.accuracy:.3f} |",
        f"| Majority baseline | {majority_baseline:.3f} |",
        f"| Precision | {oos_metrics.precision:.3f} |",
        f"| Recall | {oos_metrics.recall:.3f} |",
        f"| ROC AUC | {oos_metrics.roc_auc if oos_metrics.roc_auc is not None else 'n/a'} |",
        "", "## In-training metrics (for reference, NOT the out-of-sample result above)", "",
        f"| Metric | Value |", f"|---|---|",
        f"| Accuracy | {result.metrics.accuracy:.3f} |",
        f"| Hypothesis outcome | {result.hypothesis_outcome.value} |",
        "", "## News features used", "",
        "\n".join(f"- `{name}`" for name in news_features) if news_features else "(none found)",
    ]
    report = "\n".join(lines)
    print("\n" + report)
    report_path = f"../../docs/ml-candidate-report-{now.date().isoformat()}-us-news{REPORT_FILENAME_SUFFIX}.md"
    with open(report_path, "w") as f:
        f.write(report + "\n")


if __name__ == "__main__":
    main()
