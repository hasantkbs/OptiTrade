"""
OptiTrade Continuous Learning — accuracy computation.

Pure functions turning a list of already-evaluated
`EngineOutcomeRecord`s (one engine, one rolling window) into a single
`AccuracyMetrics` snapshot: directional accuracy, macro precision/
recall (reusing `scikit-learn` - already an existing project
dependency - rather than hand-rolling a confusion matrix), calibration
error/reliability (`calibration.py`), and mean-absolute-error for both
expected return and expected volatility.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sklearn.metrics import precision_score, recall_score

from decision_engine.models import Prediction
from learning import calibration
from learning.config import LearningConfig
from learning.models import AccuracyMetrics, EngineOutcomeRecord, RollingWindow

_LABELS = [Prediction.BUY.value, Prediction.HOLD.value, Prediction.SELL.value]

_WINDOW_DAYS = {
    RollingWindow.SEVEN_DAY: 7,
    RollingWindow.THIRTY_DAY: 30,
    RollingWindow.NINETY_DAY: 90,
}


def window_start(window: RollingWindow, now: datetime) -> Optional[datetime]:
    """The earliest `decided_at` a sample may have to fall inside
    `window` as of `now`. `None` for `LIFETIME` (no lower bound)."""
    if window == RollingWindow.LIFETIME:
        return None
    return now - timedelta(days=_WINDOW_DAYS[window])


def _actual_label(outcome: EngineOutcomeRecord, hold_band_pct: float) -> str:
    half_band = hold_band_pct / 2
    if outcome.actual_return > half_band:
        return Prediction.BUY.value
    if outcome.actual_return < -half_band:
        return Prediction.SELL.value
    return Prediction.HOLD.value


def compute_accuracy_metrics(
    engine_name: str,
    engine_version: str,
    window: RollingWindow,
    outcomes: List[EngineOutcomeRecord],
    config: Optional[LearningConfig] = None,
) -> AccuracyMetrics:
    """Computes one `AccuracyMetrics` snapshot from `outcomes` (already
    filtered to the engine/version/window in question, evaluated or
    not - unevaluated rows are ignored here)."""
    config = config or LearningConfig()
    evaluated = [o for o in outcomes if o.evaluated and o.correct is not None]

    if not evaluated:
        return AccuracyMetrics(
            engine_name=engine_name, engine_version=engine_version, window=window,
            sample_count=0, accuracy=0.0, precision=0.0, recall=0.0,
            calibration_error=0.0, confidence_reliability=1.0,
            expected_return_error=0.0, volatility_error=0.0,
        )

    accuracy = sum(1 for o in evaluated if o.correct) / len(evaluated)

    y_true = [_actual_label(o, config.hold_band_pct) for o in evaluated]
    y_pred = [o.prediction.value for o in evaluated]
    precision = float(precision_score(y_true, y_pred, labels=_LABELS, average="macro", zero_division=0))
    recall = float(recall_score(y_true, y_pred, labels=_LABELS, average="macro", zero_division=0))

    calibration_error = calibration.expected_calibration_error(evaluated, config.calibration_bins)
    confidence_reliability = calibration.confidence_reliability_score(evaluated, config.calibration_bins)

    return_errors = [abs(o.expected_return - o.actual_return) for o in evaluated]
    volatility_errors = [abs(o.expected_volatility - o.actual_volatility) for o in evaluated]

    return AccuracyMetrics(
        engine_name=engine_name, engine_version=engine_version, window=window,
        sample_count=len(evaluated), accuracy=accuracy, precision=precision, recall=recall,
        calibration_error=calibration_error, confidence_reliability=confidence_reliability,
        expected_return_error=sum(return_errors) / len(return_errors),
        volatility_error=sum(volatility_errors) / len(volatility_errors),
    )
