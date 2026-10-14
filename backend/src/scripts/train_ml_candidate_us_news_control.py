"""OptiTrade — same-split control + significance test for attempt 7
(Technical + SEC + News).

Usage (from backend/src):
  python scripts/train_ml_candidate_us_news_control.py

Attempt 7 (train_ml_candidate_us_news.py) was the first of 7 attempts
to beat its baseline (0.460 vs 0.445, ROC-AUC 0.537) - but on a
notably smaller held-out sample (2352) than prior attempts. This
trains TWO models on the IDENTICAL chronological train/held-out split
- one with News features, one without - then runs two significance
tests on the SAME held-out predictions (paired, not independent-sample
tests, since both models were scored on the identical 2,352 samples):

  - McNemar's test (with continuity correction) on accuracy: compares
    how often each model is uniquely right where the other is wrong -
    the standard paired test for "do two classifiers' accuracies
    differ" on one shared test set.
  - A paired bootstrap (2,000 resamples) for both the accuracy gap and
    the ROC-AUC gap: resamples the held-out indices with replacement,
    recomputes each model's accuracy/AUC on the SAME resampled indices
    (no retraining - both models' predictions are already fixed), and
    reports the 95% CI and the one-sided p-value (fraction of resamples
    where News does not help).

Deliberately skips model registry/experiment/calibration/SHAP
bookkeeping (unlike every other script here) - this is a diagnostic
comparison, not a candidate for promotion.
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

import numpy as np
import pandas as pd
from scipy.stats import chi2
from sklearn.metrics import accuracy_score, roc_auc_score

from core.market_config import US_SYMBOLS
from ml_training.config import MLTrainingConfig
from ml_training.datasets.builder import DatasetBuilder
from ml_training.evaluation.evaluator import ModelEvaluator
from ml_training.features.extractor import FeatureExtractor
from ml_training.models import DatasetType, LabelName, ModelAlgorithm, TaskType
from ml_training.service import _samples_to_arrays
from ml_training.training.service import create_trainer
from scripts.train_ml_candidate import CachingPriceFetcher

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

HORIZON_DAYS = 5
SYMBOLS = list(US_SYMBOLS.keys())
_NEWS_COVERAGE_START = datetime(2025, 10, 29, tzinfo=timezone.utc)
_BOOTSTRAP_ITERATIONS = 2000
_BOOTSTRAP_SEED = 42  # fixed so this script's own output is itself reproducible


def _fit_and_predict(
    label: str, feature_names: List[str], train_samples, held_out_samples, config,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Returns (y_true, y_pred, y_proba, classes) on the held-out set -
    the raw arrays the significance tests below need, alongside the
    same printed summary the original control run showed. `classes` is
    the trainer's own label order for `y_proba`'s columns - never
    inferred via np.unique, since that would only coincidentally match
    if train/held-out happened to share every class."""
    X_train, y_train, _ = _samples_to_arrays(train_samples, feature_names, LabelName.DIRECTION)
    X_oos, y_oos, returns_oos = _samples_to_arrays(held_out_samples, feature_names, LabelName.DIRECTION)

    trainer = create_trainer(ModelAlgorithm.XGBOOST, TaskType.CLASSIFICATION, feature_names, config=config)
    trainer.fit(X_train, y_train)  # no val split for this diagnostic comparison - no early stopping either side

    evaluator = ModelEvaluator(config=config)
    metrics = evaluator.evaluate(trainer, X_oos, y_oos, actual_returns=returns_oos)
    counts = pd.Series(y_oos).value_counts().tolist()
    majority_baseline = max(counts) / len(y_oos) if len(y_oos) else 0.0

    print(f"\n--- {label} ({len(feature_names)} features) ---")
    print(f"Accuracy: {metrics.accuracy:.3f} | Majority baseline: {majority_baseline:.3f}")
    print(f"Precision: {metrics.precision:.3f} | Recall: {metrics.recall:.3f}")
    print(f"ROC AUC: {metrics.roc_auc}")

    y_pred = trainer.predict(X_oos)
    y_proba = trainer.predict_proba(X_oos)
    return y_oos, y_pred, y_proba, trainer.classes_


def _mcnemar_test(y_true: np.ndarray, pred_a: np.ndarray, pred_b: np.ndarray) -> Tuple[int, int, float, float]:
    """(b, c, statistic, p_value) where b = A-right/B-wrong count,
    c = A-wrong/B-right count - the two discordant cells McNemar's
    test is actually about; the concordant cells (both right, both
    wrong) carry no information on which model is better."""
    correct_a = pred_a == y_true
    correct_b = pred_b == y_true
    b = int(np.sum(correct_a & ~correct_b))
    c = int(np.sum(~correct_a & correct_b))
    if b + c == 0:
        return b, c, 0.0, 1.0
    statistic = (abs(b - c) - 1) ** 2 / (b + c)
    p_value = 1 - chi2.cdf(statistic, df=1)
    return b, c, statistic, p_value


def _bootstrap_gap(
    y_true: np.ndarray, pred_with: np.ndarray, proba_with: np.ndarray,
    pred_without: np.ndarray, proba_without: np.ndarray,
) -> None:
    rng = np.random.default_rng(_BOOTSTRAP_SEED)
    n = len(y_true)
    accuracy_gaps = []
    auc_gaps = []
    skipped = 0

    for _ in range(_BOOTSTRAP_ITERATIONS):
        idx = rng.integers(0, n, size=n)
        y_s = y_true[idx]
        if len(np.unique(y_s)) < 2:
            skipped += 1
            continue
        accuracy_gaps.append(
            accuracy_score(y_s, pred_with[idx]) - accuracy_score(y_s, pred_without[idx])
        )
        try:
            auc_with = roc_auc_score(y_s, proba_with[idx], multi_class="ovr", average="macro")
            auc_without = roc_auc_score(y_s, proba_without[idx], multi_class="ovr", average="macro")
            auc_gaps.append(auc_with - auc_without)
        except ValueError:
            # A resample missing one class entirely for the OVR AUC call -
            # excluded from the AUC distribution only, accuracy still counted.
            continue

    accuracy_gaps = np.array(accuracy_gaps)
    auc_gaps = np.array(auc_gaps)

    print(f"\n--- Bootstrap ({_BOOTSTRAP_ITERATIONS} resamples, {skipped} skipped for missing classes) ---")
    print(
        f"Accuracy gap (With - Without): mean={accuracy_gaps.mean():.4f}, "
        f"95% CI=[{np.percentile(accuracy_gaps, 2.5):.4f}, {np.percentile(accuracy_gaps, 97.5):.4f}], "
        f"P(gap <= 0)={np.mean(accuracy_gaps <= 0):.4f}"
    )
    print(
        f"ROC-AUC gap (With - Without): mean={auc_gaps.mean():.4f}, "
        f"95% CI=[{np.percentile(auc_gaps, 2.5):.4f}, {np.percentile(auc_gaps, 97.5):.4f}], "
        f"P(gap <= 0)={np.mean(auc_gaps <= 0):.4f} (n={len(auc_gaps)})"
    )


def _per_class_breakdown(label: str, y_true: np.ndarray, y_pred: np.ndarray, y_proba: np.ndarray, classes: np.ndarray) -> None:
    """Confusion matrix + per-class precision/recall/support + per-class
    one-vs-rest AUC. Macro-averaged ROC-AUC (what the significance test
    above compares) weighs every class equally regardless of how many
    held-out samples it has - a class-concentrated effect can move
    accuracy (which IS sample-weighted) a lot while barely moving the
    macro-AUC average, or even dragging it down on a thin class."""
    from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, roc_auc_score

    print(f"\n--- {label}: confusion matrix (rows=true, cols=predicted) ---")
    cm = confusion_matrix(y_true, y_pred, labels=classes)
    header = "        " + "  ".join(f"{c:>6}" for c in classes)
    print(header)
    for i, c in enumerate(classes):
        print(f"{c:>6}  " + "  ".join(f"{v:>6d}" for v in cm[i]))

    precision, recall, f1, support = precision_recall_fscore_support(y_true, y_pred, labels=classes, zero_division=0)
    print(f"\n--- {label}: per-class precision/recall/f1/support/AUC ---")
    for i, c in enumerate(classes):
        y_bin = (y_true == c).astype(int)
        try:
            class_auc = roc_auc_score(y_bin, y_proba[:, i])
        except ValueError:
            class_auc = float("nan")
        print(
            f"{c:>6}: precision={precision[i]:.3f} recall={recall[i]:.3f} "
            f"f1={f1[i]:.3f} support={support[i]:4d} one-vs-rest AUC={class_auc:.4f}"
        )


def _confidence_stratified_accuracy(label: str, y_true: np.ndarray, y_pred: np.ndarray, y_proba: np.ndarray) -> None:
    """Splits held-out samples into confidence terciles by this model's
    OWN max predicted probability, and reports accuracy within each
    bucket - tests directly whether a model's accuracy gain is
    concentrated in cases it was already confident about (consistent
    with accuracy moving while ranking/AUC does not) versus genuinely
    hard, low-confidence cases (which would show up in AUC too)."""
    from sklearn.metrics import accuracy_score

    confidence = y_proba.max(axis=1)
    low_cut, high_cut = np.percentile(confidence, [33.33, 66.67])
    buckets = {
        "low": confidence <= low_cut,
        "mid": (confidence > low_cut) & (confidence <= high_cut),
        "high": confidence > high_cut,
    }
    print(f"\n--- {label}: accuracy by own-confidence tercile ---")
    for name, mask in buckets.items():
        if mask.sum() == 0:
            continue
        acc = accuracy_score(y_true[mask], y_pred[mask])
        print(f"{name:>4} confidence (n={int(mask.sum()):4d}, mean conf={confidence[mask].mean():.3f}): accuracy={acc:.3f}")


def _diagnose_discordant_cases(
    y_true: np.ndarray, pred_with: np.ndarray, proba_with: np.ndarray,
    pred_without: np.ndarray, proba_without: np.ndarray, classes: np.ndarray,
) -> None:
    """Directly inspects the McNemar discordant sets (b: With uniquely
    right, c: Without uniquely right) - which true class they fall on,
    and how confident the With-News model was on them relative to its
    own overall average. If b-cases cluster on the majority class and/or
    carry below-average confidence, that is NOT the 'reinforcing already-
    easy calls' pattern - it would mean News is winning hard, close
    calls, which the macro-AUC's equal per-class weighting can still
    fail to reward if it's concentrated on one class."""
    correct_with = pred_with == y_true
    correct_without = pred_without == y_true
    b_mask = correct_with & ~correct_without
    c_mask = ~correct_with & correct_without

    conf_with = proba_with.max(axis=1)
    conf_without = proba_without.max(axis=1)

    print("\n--- Discordant case breakdown ---")
    print(f"Overall With-model confidence (mean max-proba): {conf_with.mean():.3f}")
    print(f"Overall Without-model confidence (mean max-proba): {conf_without.mean():.3f}")

    b_true_counts = pd.Series(y_true[b_mask]).value_counts().reindex(classes, fill_value=0)
    c_true_counts = pd.Series(y_true[c_mask]).value_counts().reindex(classes, fill_value=0)
    overall_true_counts = pd.Series(y_true).value_counts().reindex(classes, fill_value=0)

    print(f"\nTrue-class distribution overall (n={len(y_true)}):")
    for c in classes:
        print(f"  {c:>6}: {overall_true_counts[c]:4d} ({overall_true_counts[c] / len(y_true):.1%})")

    print(f"\nTrue-class distribution of b-cases (With right, Without wrong, n={int(b_mask.sum())}):")
    for c in classes:
        print(f"  {c:>6}: {b_true_counts[c]:4d} ({b_true_counts[c] / max(b_mask.sum(), 1):.1%})")
    print(f"With-model's own confidence on its b-case predictions: {conf_with[b_mask].mean():.3f} "
          f"(vs its overall {conf_with.mean():.3f})")

    print(f"\nTrue-class distribution of c-cases (Without right, With wrong, n={int(c_mask.sum())}):")
    for c in classes:
        print(f"  {c:>6}: {c_true_counts[c]:4d} ({c_true_counts[c] / max(c_mask.sum(), 1):.1%})")
    print(f"With-model's own confidence on its c-case (wrong) predictions: {conf_with[c_mask].mean():.3f} "
          f"(vs its overall {conf_with.mean():.3f})")


def main() -> None:
    config = MLTrainingConfig.from_env()
    now = datetime.now(timezone.utc)
    train_start = _NEWS_COVERAGE_START
    held_out_start = now - timedelta(days=90)
    train_end_date = held_out_start - timedelta(days=1)

    print("=" * 65)
    print("Attempt 7 control: same split, News features in vs. out")
    print(f"Train: [{train_start.date().isoformat()}, {train_end_date.date().isoformat()}] | "
          f"Held-out: [{held_out_start.date().isoformat()}, {now.date().isoformat()}]")
    print("=" * 65)

    price_fetcher = CachingPriceFetcher(SYMBOLS, train_start, now)
    builder = DatasetBuilder(feature_extractor=FeatureExtractor(), config=config, price_fetcher=price_fetcher)

    print("\nBuilding train samples...")
    train_samples, _ = builder.build(SYMBOLS, DatasetType.TRADER, train_start, train_end_date, horizons_days=[HORIZON_DAYS])
    print(f"{len(train_samples)} train samples built.")

    print("Building held-out samples...")
    held_out_samples, _ = builder.build(SYMBOLS, DatasetType.TRADER, held_out_start, now, horizons_days=[HORIZON_DAYS])
    print(f"{len(held_out_samples)} held-out samples built.")

    all_features = sorted({name for sample in train_samples for name in sample.features})
    news_features = [n for n in all_features if n.startswith("news_")]
    restricted_features = [n for n in all_features if n not in news_features]

    print(f"\nFull feature set: {len(all_features)} ({len(news_features)} News)")
    print(f"Restricted (no News): {len(restricted_features)}")

    y_true_with, pred_with, proba_with, classes_with = _fit_and_predict(
        "WITH News", all_features, train_samples, held_out_samples, config,
    )
    y_true_without, pred_without, proba_without, classes_without = _fit_and_predict(
        "WITHOUT News", restricted_features, train_samples, held_out_samples, config,
    )
    # Both arms were built from the SAME held_out_samples list/order via
    # the SAME _samples_to_arrays call shape - y_true must be identical
    # between the two arms for the paired tests below to be valid.
    assert np.array_equal(y_true_with, y_true_without), "held-out label order diverged between the two arms"
    assert np.array_equal(classes_with, classes_without), "label encoder class order diverged between the two arms"
    y_true = y_true_with
    classes = classes_with

    b, c, statistic, p_value = _mcnemar_test(y_true, pred_with, pred_without)
    print(f"\n--- McNemar's test (accuracy, paired) ---")
    print(f"With-right/Without-wrong: {b} | Without-right/With-wrong: {c}")
    print(f"Statistic: {statistic:.4f} | p-value: {p_value:.4f}")

    _bootstrap_gap(y_true, pred_with, proba_with, pred_without, proba_without)

    print("\n" + "=" * 65)
    print("Diagnostics: why did accuracy move but not ROC-AUC?")
    print("=" * 65)
    _per_class_breakdown("WITH News", y_true, pred_with, proba_with, classes)
    _per_class_breakdown("WITHOUT News", y_true, pred_without, proba_without, classes)
    _confidence_stratified_accuracy("WITH News", y_true, pred_with, proba_with)
    _confidence_stratified_accuracy("WITHOUT News", y_true, pred_without, proba_without)
    _diagnose_discordant_cases(y_true, pred_with, proba_with, pred_without, proba_without, classes)


if __name__ == "__main__":
    main()
