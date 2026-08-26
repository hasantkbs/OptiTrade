"""
OptiTrade Continuous Learning — configuration.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from learning.models import WeightingPolicy

_POLICY_BY_NAME = {policy.value: policy for policy in WeightingPolicy}


@dataclass(frozen=True)
class LearningConfig:
    """Runtime settings for the whole Continuous Learning system."""

    # Evaluation
    evaluation_horizon_days: int = 5
    hold_band_pct: float = 1.0
    evaluation_batch_size: int = 200

    # Accuracy / calibration
    baseline_accuracy: float = 0.5
    calibration_bins: int = 10

    # Weighting
    weighting_policy: WeightingPolicy = WeightingPolicy.EXPONENTIAL_DECAY
    weighting_window: str = "30d"
    min_weight: float = 0.2
    max_weight: float = 3.0
    max_weight_step: float = 0.15
    exponential_smoothing_factor: float = 0.3
    bayesian_prior_strength: float = 10.0
    min_samples_for_weighting: int = 5

    # Drift detection
    min_samples_for_drift: int = 10
    drift_improve_threshold: float = 0.05
    drift_degrade_threshold: float = 0.05
    drift_unstable_variance_threshold: float = 0.02
    drift_recent_window: str = "7d"
    drift_baseline_window: str = "30d"

    # Promotion
    promotion_margin: float = 0.03
    min_samples_for_promotion: int = 20

    accuracy_feature_name: str = "engine_accuracy_score"

    @classmethod
    def from_env(cls) -> "LearningConfig":
        load_dotenv()
        return cls(
            evaluation_horizon_days=int(os.getenv("LEARNING_EVALUATION_HORIZON_DAYS", "5")),
            hold_band_pct=float(os.getenv("LEARNING_HOLD_BAND_PCT", "1.0")),
            evaluation_batch_size=int(os.getenv("LEARNING_EVALUATION_BATCH_SIZE", "200")),
            baseline_accuracy=float(os.getenv("LEARNING_BASELINE_ACCURACY", "0.5")),
            calibration_bins=int(os.getenv("LEARNING_CALIBRATION_BINS", "10")),
            weighting_policy=_POLICY_BY_NAME[
                os.getenv("LEARNING_WEIGHTING_POLICY", WeightingPolicy.EXPONENTIAL_DECAY.value)
            ],
            weighting_window=os.getenv("LEARNING_WEIGHTING_WINDOW", "30d"),
            min_weight=float(os.getenv("LEARNING_MIN_WEIGHT", "0.2")),
            max_weight=float(os.getenv("LEARNING_MAX_WEIGHT", "3.0")),
            max_weight_step=float(os.getenv("LEARNING_MAX_WEIGHT_STEP", "0.15")),
            exponential_smoothing_factor=float(os.getenv("LEARNING_EXPONENTIAL_SMOOTHING_FACTOR", "0.3")),
            bayesian_prior_strength=float(os.getenv("LEARNING_BAYESIAN_PRIOR_STRENGTH", "10.0")),
            min_samples_for_weighting=int(os.getenv("LEARNING_MIN_SAMPLES_FOR_WEIGHTING", "5")),
            min_samples_for_drift=int(os.getenv("LEARNING_MIN_SAMPLES_FOR_DRIFT", "10")),
            drift_improve_threshold=float(os.getenv("LEARNING_DRIFT_IMPROVE_THRESHOLD", "0.05")),
            drift_degrade_threshold=float(os.getenv("LEARNING_DRIFT_DEGRADE_THRESHOLD", "0.05")),
            drift_unstable_variance_threshold=float(
                os.getenv("LEARNING_DRIFT_UNSTABLE_VARIANCE_THRESHOLD", "0.02")
            ),
            drift_recent_window=os.getenv("LEARNING_DRIFT_RECENT_WINDOW", "7d"),
            drift_baseline_window=os.getenv("LEARNING_DRIFT_BASELINE_WINDOW", "30d"),
            promotion_margin=float(os.getenv("LEARNING_PROMOTION_MARGIN", "0.03")),
            min_samples_for_promotion=int(os.getenv("LEARNING_MIN_SAMPLES_FOR_PROMOTION", "20")),
            accuracy_feature_name=os.getenv("LEARNING_ACCURACY_FEATURE_NAME", "engine_accuracy_score"),
        )
