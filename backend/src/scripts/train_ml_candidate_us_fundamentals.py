"""OptiTrade — ML candidate training, US equities, Technical + SEC Fundamentals.

Usage (from backend/src):
  python scripts/train_ml_candidate_us_fundamentals.py

Prerequisites: scripts/backfill_feature_store.py --symbols us AND
scripts/backfill_sec_fundamentals.py must already have been run.

Four prior direction-label attempts (docs/ml-candidate-report-2026-10-
01.md, -2026-10-03.md, -2026-10-03-derived-features.md, and the
volatility-regression attempt) all used the original 15-BIST+7-crypto
basket with ONLY Technical features (17, or 49 with derived features)
and converged on no reliable signal. Fundamental/News features were
never tried - blocked because yfinance only gives current-snapshot
data, and a paid-vendor search (docs/data-vendor-research-2026-10-13
.md) found no vendor offering confirmed point-in-time BIST fundamentals
at any price. This is the first attempt to actually test the
Fundamental-features hypothesis, on the one basket where genuine
point-in-time data is available for free (US equities via SEC EDGAR -
see scripts/backfill_sec_fundamentals.py's own docstring for why this
is leakage-safe).

Same label (direction), horizon_days=5, and algorithm (XGBoost) as the
original attempts, for direct comparability on the metric that matters
(accuracy vs. majority baseline) - the basket itself necessarily
differs (US equities vs. BIST+crypto), so this is not a perfectly
isolated A/B test of "fundamentals vs. no fundamentals" on identical
data; it tests whether Technical+Fundamental together show any signal
at all on a basket where fundamentals are real. A technical-only
control on this SAME US basket is deliberately deferred unless this
run shows a result clearly worth isolating further (YAGNI) - three
prior attempts already established "technical alone shows no signal"
as a strong, repeated prior on a different basket.

FeatureExtractor auto-discovers every Feature Store feature name per
symbol (see its own docstring) - the SEC-backfilled `sec_*` features
and the Technical engine's 17 features are both picked up automatically
with zero ml_training package changes.
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

from core.market_config import US_SYMBOLS
from engines.technical.config import FEATURE_TREND_STRENGTH
from feature_store.service import get_default_feature_store_service
from ml_training.config import MLTrainingConfig
from ml_training.datasets.builder import DatasetBuilder
from ml_training.datasets.service import DatasetService
from ml_training.evaluation.evaluator import ModelEvaluator
from ml_training.features.extractor import FeatureExtractor
from ml_training.models import DatasetType, LabelName, ModelAlgorithm
from ml_training.service import MLTrainingService, _samples_to_arrays
from ml_training.training.service import create_trainer
from scripts.train_ml_candidate import CachingPriceFetcher, _earliest_feature_date

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

_AUTHOR = "train_ml_candidate_us_fundamentals_script"
HORIZON_DAYS = 5
REPORT_FILENAME_SUFFIX = os.getenv("TRAIN_ML_CANDIDATE_REPORT_SUFFIX", "")
SYMBOLS = list(US_SYMBOLS.keys())


def main() -> None:
    config = MLTrainingConfig.from_env()
    now = datetime.now(timezone.utc)
    train_end_date = now - timedelta(days=180)
    train_start = train_end_date - timedelta(days=730)

    print("=" * 65)
    print("OptiTrade - ML Candidate Training (US equities, Technical + SEC Fundamentals)")
    print(f"Train: [{train_start.date().isoformat()}, {train_end_date.date().isoformat()}] | "
          f"Held-out eval: ({train_end_date.date().isoformat()}, {now.date().isoformat()}]")
    print(f"Symbols: {len(SYMBOLS)} | horizon_days={HORIZON_DAYS} | algorithm=xgboost | label=direction")
    print("=" * 65)

    earliest_available = _earliest_feature_date(SYMBOLS)
    if earliest_available is not None and earliest_available.date() > train_start.date():
        print(
            f"UYARI: Feature Store coverage starts {earliest_available.date().isoformat()}, "
            f"after the computed train_start {train_start.date().isoformat()} - "
            f"the real training window is narrower than nominally computed."
        )

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
    sec_features = sorted(name for name in feature_names if name.startswith("sec_"))
    print(f"CANDIDATE kaydedildi: model_id={result.registry_entry.model_id}")
    print(f"Toplam özellik sayısı: {len(feature_names)} (bunlardan {len(sec_features)} SEC fundamentals)")
    print(f"In-training accuracy: {result.metrics.accuracy:.3f}")
    print(f"Hipotez sonucu: {result.hypothesis_outcome.value}")

    print("\nGerçek out-of-sample değerlendirme çalıştırılıyor...")
    held_out_start = train_end_date + timedelta(days=1)
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
    sec_coverage = sum(1 for sample in held_out_samples if any(f in sample.features for f in sec_features)) if sec_features else 0

    lines = [
        f"# ML Candidate Report — {now.date().isoformat()} (US equities, Technical + SEC Fundamentals)", "",
        f"Model: `{result.registry_entry.model_id}` (algorithm=xgboost, label=direction, horizon_days={HORIZON_DAYS})",
        f"Promotion state: `{result.registry_entry.promotion_state.value}` (CANDIDATE only - no SHADOW/ACTIVE in this run)",
        f"Basket: {len(SYMBOLS)} US equities ({', '.join(SYMBOLS)})",
        "",
        "## Held-out out-of-sample evaluation",
        "",
        f"Train window: [{train_start.date().isoformat()}, {train_end_date.date().isoformat()}]",
        f"Held-out window (strictly after train_end_date): [{held_out_start.date().isoformat()}, {now.date().isoformat()}]",
        f"Held-out samples: {len(held_out_samples)} ({sec_coverage} with at least one SEC fundamental feature present)",
        f"Total features: {len(feature_names)} ({len(sec_features)} SEC fundamentals, {len(feature_names) - len(sec_features)} Technical)",
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
        "", "## SEC fundamental features used", "",
        "\n".join(f"- `{name}`" for name in sec_features) if sec_features else "(none found in the trained feature list)",
    ]
    report = "\n".join(lines)
    print("\n" + report)
    report_path = f"../../docs/ml-candidate-report-{now.date().isoformat()}-us-fundamentals{REPORT_FILENAME_SUFFIX}.md"
    with open(report_path, "w") as f:
        f.write(report + "\n")


if __name__ == "__main__":
    main()
