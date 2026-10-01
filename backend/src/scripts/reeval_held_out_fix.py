"""One-off re-evaluation: corrects the train/held-out boundary overlap
bug in train_ml_candidate.py's original run WITHOUT retraining.

Context: the original run (model_id=xgb-dir-5d-eda870a7) built its
held-out dataset with start=train_end_date, but DatasetBuilder.build's
cursor loop is inclusive on both ends, so samples dated exactly
train_end_date leaked into BOTH the training set and the "held-out"
set. This script reuses the already-trained+saved model artifact
(loaded via the registry, exactly as train_ml_candidate.py's own
held-out evaluation step already does) and rebuilds ONLY the held-out
dataset, now starting at train_end_date + 1 day - a genuine, not just
nominal, no-overlap held-out window - then re-evaluates.

Does NOT retrain, does NOT touch the registry/promotion state.
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from ml_training.config import MLTrainingConfig
from ml_training.datasets.builder import DatasetBuilder
from ml_training.evaluation.evaluator import ModelEvaluator
from ml_training.features.extractor import FeatureExtractor
from ml_training.models import DatasetType, LabelName, ModelAlgorithm, task_type_for_label
from ml_training.registry.service import ModelRegistryService
from ml_training.service import _samples_to_arrays
from ml_training.training.service import create_trainer
from research.ml_trainer import SYMBOLS
from scripts.train_ml_candidate import CachingPriceFetcher, HORIZON_DAYS

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

MODEL_ID = "xgb-dir-5d-eda870a7"


def main() -> None:
    config = MLTrainingConfig.from_env()
    now = datetime.now(timezone.utc)
    train_end_date = now - timedelta(days=180)
    train_start = train_end_date - timedelta(days=730)
    held_out_start = train_end_date + timedelta(days=1)  # the fix: strictly after train_end_date

    print("=" * 65)
    print("OptiTrade - ML Candidate held-out FIX re-evaluation (no retraining)")
    print(f"Train window (unchanged, model already trained on this): [{train_start.date().isoformat()}, {train_end_date.date().isoformat()}]")
    print(f"Held-out window (FIXED - strictly after train_end_date): [{held_out_start.date().isoformat()}, {now.date().isoformat()}]")
    print("=" * 65)

    registry_entry = ModelRegistryService().get(MODEL_ID)
    if registry_entry is None:
        raise RuntimeError(f"model_id {MODEL_ID!r} not found in ml_training_model_registry")
    print(f"Loaded registry entry: model_id={registry_entry.model_id}, promotion_state={registry_entry.promotion_state.value}")

    price_fetcher = CachingPriceFetcher(SYMBOLS, train_start, now)
    held_out_builder = DatasetBuilder(feature_extractor=FeatureExtractor(), config=config, price_fetcher=price_fetcher)
    held_out_samples, held_out_version = held_out_builder.build(
        SYMBOLS, DatasetType.TRADER, start=held_out_start, end=now, horizons_days=[HORIZON_DAYS],
    )
    print(f"Held-out samples (FIXED window): {len(held_out_samples)}")

    task_type = task_type_for_label(LabelName.DIRECTION)
    trainer = create_trainer(ModelAlgorithm.XGBOOST, task_type, registry_entry.feature_list, config=config)
    trainer.load(registry_entry.artifact_path)

    X_oos, y_oos, returns_oos = _samples_to_arrays(held_out_samples, registry_entry.feature_list, LabelName.DIRECTION)
    evaluator = ModelEvaluator(config=config)
    oos_metrics = evaluator.evaluate(trainer, X_oos, y_oos, actual_returns=returns_oos)

    counts = pd.Series(y_oos).value_counts().tolist()
    majority_baseline = max(counts) / len(y_oos) if len(y_oos) else 0.0

    lines = [
        f"# ML Candidate Report — {now.date().isoformat()}", "",
        f"Model: `{registry_entry.model_id}` (algorithm=xgboost, label=direction, horizon_days={HORIZON_DAYS})",
        f"Promotion state: `{registry_entry.promotion_state.value}` (CANDIDATE only - no SHADOW/ACTIVE in this run)",
        "", "## Held-out out-of-sample evaluation", "",
        f"Train window: [{train_start.date().isoformat()}, {train_end_date.date().isoformat()}]",
        f"Held-out window (strictly after train_end_date): [{held_out_start.date().isoformat()}, {now.date().isoformat()}]",
        f"Held-out samples: {len(held_out_samples)}", "",
        f"| Metric | Value |", f"|---|---|",
        f"| Accuracy | {oos_metrics.accuracy:.3f} |",
        f"| Majority baseline | {majority_baseline:.3f} |",
        f"| Precision | {oos_metrics.precision:.3f} |",
        f"| Recall | {oos_metrics.recall:.3f} |",
    ]
    report = "\n".join(lines)
    print("\n" + report)


if __name__ == "__main__":
    main()
