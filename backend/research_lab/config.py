"""
OptiTrade Research Lab — configuration.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class ResearchLabConfig:
    """Runtime settings for the whole Research Lab."""

    # Backtesting
    walk_forward_train_window_days: int = 90
    walk_forward_test_window_days: int = 30
    rolling_window_days: int = 60
    rolling_window_step_days: int = 30
    purged_cv_n_folds: int = 5
    purge_embargo_days: int = 2
    stress_test_shock_pct: float = -10.0
    out_of_sample_ratio: float = 0.2
    min_samples_for_backtest_fold: int = 5
    risk_free_rate: float = 0.0

    # Benchmarking
    significance_level: float = 0.05

    # Promotion
    promotion_margin: float = 0.03
    reject_margin: float = 0.03
    min_samples_for_promotion_decision: int = 20

    # Reports
    weekly_report_lookback_days: int = 7
    monthly_report_lookback_days: int = 30

    @classmethod
    def from_env(cls) -> "ResearchLabConfig":
        load_dotenv()
        return cls(
            walk_forward_train_window_days=int(os.getenv("RESEARCH_LAB_WALK_FORWARD_TRAIN_WINDOW_DAYS", "90")),
            walk_forward_test_window_days=int(os.getenv("RESEARCH_LAB_WALK_FORWARD_TEST_WINDOW_DAYS", "30")),
            rolling_window_days=int(os.getenv("RESEARCH_LAB_ROLLING_WINDOW_DAYS", "60")),
            rolling_window_step_days=int(os.getenv("RESEARCH_LAB_ROLLING_WINDOW_STEP_DAYS", "30")),
            purged_cv_n_folds=int(os.getenv("RESEARCH_LAB_PURGED_CV_N_FOLDS", "5")),
            purge_embargo_days=int(os.getenv("RESEARCH_LAB_PURGE_EMBARGO_DAYS", "2")),
            stress_test_shock_pct=float(os.getenv("RESEARCH_LAB_STRESS_TEST_SHOCK_PCT", "-10.0")),
            out_of_sample_ratio=float(os.getenv("RESEARCH_LAB_OUT_OF_SAMPLE_RATIO", "0.2")),
            min_samples_for_backtest_fold=int(os.getenv("RESEARCH_LAB_MIN_SAMPLES_FOR_BACKTEST_FOLD", "5")),
            risk_free_rate=float(os.getenv("RESEARCH_LAB_RISK_FREE_RATE", "0.0")),
            significance_level=float(os.getenv("RESEARCH_LAB_SIGNIFICANCE_LEVEL", "0.05")),
            promotion_margin=float(os.getenv("RESEARCH_LAB_PROMOTION_MARGIN", "0.03")),
            reject_margin=float(os.getenv("RESEARCH_LAB_REJECT_MARGIN", "0.03")),
            min_samples_for_promotion_decision=int(
                os.getenv("RESEARCH_LAB_MIN_SAMPLES_FOR_PROMOTION_DECISION", "20")
            ),
            weekly_report_lookback_days=int(os.getenv("RESEARCH_LAB_WEEKLY_REPORT_LOOKBACK_DAYS", "7")),
            monthly_report_lookback_days=int(os.getenv("RESEARCH_LAB_MONTHLY_REPORT_LOOKBACK_DAYS", "30")),
        )
