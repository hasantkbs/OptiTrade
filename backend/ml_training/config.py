"""OptiTrade ML Training Platform — configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv


def _parse_int_list(value: str) -> List[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class MLTrainingConfig:
    """Runtime settings for the whole ML Training Platform."""

    # Datasets / horizons
    trader_horizons_days: List[int] = field(default_factory=lambda: [1, 3, 5])
    investor_horizons_days: List[int] = field(default_factory=lambda: [30, 90, 180])
    max_symbols_per_dataset: int = 50

    # Labels - reuses the exact 2.0% support/resistance proximity
    # threshold `engines/technical/market_structure.py` already
    # defines, so "near resistance/support" means the same thing here
    # as it does to the live Technical Engine.
    direction_band_pct: float = 1.0
    proximity_threshold_pct: float = 2.0
    trend_reversal_min_move_pct: float = 1.0
    breakout_min_move_pct: float = 3.0

    # Training
    test_size: float = 0.2
    validation_size: float = 0.15
    random_state: int = 42
    early_stopping_rounds: int = 50

    # Hyperparameter optimization
    optuna_n_trials: int = 50
    optuna_n_jobs: int = 1
    optuna_timeout_seconds: int = 0  # 0 = no timeout

    # Calibration
    calibration_bins: int = 10

    # Evaluation
    risk_free_rate: float = 0.0
    hold_band_pct: float = 1.0

    # Model registry / artifacts
    model_artifact_dir: str = "ml_training_artifacts"
    min_samples_for_shadow_promotion: int = 20

    @classmethod
    def from_env(cls) -> "MLTrainingConfig":
        load_dotenv()
        return cls(
            trader_horizons_days=_parse_int_list(os.getenv("ML_TRAINING_TRADER_HORIZONS_DAYS", "1,3,5")),
            investor_horizons_days=_parse_int_list(
                os.getenv("ML_TRAINING_INVESTOR_HORIZONS_DAYS", "30,90,180")
            ),
            max_symbols_per_dataset=int(os.getenv("ML_TRAINING_MAX_SYMBOLS_PER_DATASET", "50")),
            direction_band_pct=float(os.getenv("ML_TRAINING_DIRECTION_BAND_PCT", "1.0")),
            proximity_threshold_pct=float(os.getenv("ML_TRAINING_PROXIMITY_THRESHOLD_PCT", "2.0")),
            trend_reversal_min_move_pct=float(os.getenv("ML_TRAINING_TREND_REVERSAL_MIN_MOVE_PCT", "1.0")),
            breakout_min_move_pct=float(os.getenv("ML_TRAINING_BREAKOUT_MIN_MOVE_PCT", "3.0")),
            test_size=float(os.getenv("ML_TRAINING_TEST_SIZE", "0.2")),
            validation_size=float(os.getenv("ML_TRAINING_VALIDATION_SIZE", "0.15")),
            random_state=int(os.getenv("ML_TRAINING_RANDOM_STATE", "42")),
            early_stopping_rounds=int(os.getenv("ML_TRAINING_EARLY_STOPPING_ROUNDS", "50")),
            optuna_n_trials=int(os.getenv("ML_TRAINING_OPTUNA_N_TRIALS", "50")),
            optuna_n_jobs=int(os.getenv("ML_TRAINING_OPTUNA_N_JOBS", "1")),
            optuna_timeout_seconds=int(os.getenv("ML_TRAINING_OPTUNA_TIMEOUT_SECONDS", "0")),
            calibration_bins=int(os.getenv("ML_TRAINING_CALIBRATION_BINS", "10")),
            risk_free_rate=float(os.getenv("ML_TRAINING_RISK_FREE_RATE", "0.0")),
            hold_band_pct=float(os.getenv("ML_TRAINING_HOLD_BAND_PCT", "1.0")),
            model_artifact_dir=os.getenv("ML_TRAINING_MODEL_ARTIFACT_DIR", "ml_training_artifacts"),
            min_samples_for_shadow_promotion=int(
                os.getenv("ML_TRAINING_MIN_SAMPLES_FOR_SHADOW_PROMOTION", "20")
            ),
        )
