"""
OptiTrade Continuous Learning — calibration.

Computes how well an engine's self-reported `confidence` matches its
actual empirical accuracy (a reliability diagram / Expected Calibration
Error, ECE) - a well-calibrated engine that says "80% confident" should
actually be correct about 80% of the time. Confidence reliability is
simply the inverse of ECE, kept as its own named metric for readability
in `learning.models.AccuracyMetrics`.
"""
from __future__ import annotations

from typing import List

from learning.models import EngineOutcomeRecord


def _evaluated_only(outcomes: List[EngineOutcomeRecord]) -> List[EngineOutcomeRecord]:
    return [o for o in outcomes if o.evaluated and o.correct is not None]


def expected_calibration_error(outcomes: List[EngineOutcomeRecord], num_bins: int = 10) -> float:
    """Bins predictions by confidence into `num_bins` equal-width
    buckets and returns the sample-weighted average gap between each
    bucket's empirical accuracy and its average reported confidence -
    `0.0` (perfectly calibrated) to `1.0` (maximally miscalibrated)."""
    evaluated = _evaluated_only(outcomes)
    if not evaluated:
        return 0.0

    bins: List[List[EngineOutcomeRecord]] = [[] for _ in range(num_bins)]
    for outcome in evaluated:
        index = min(num_bins - 1, int(outcome.confidence * num_bins))
        bins[index].append(outcome)

    total = len(evaluated)
    error = 0.0
    for bucket in bins:
        if not bucket:
            continue
        bucket_accuracy = sum(1 for o in bucket if o.correct) / len(bucket)
        bucket_confidence = sum(o.confidence for o in bucket) / len(bucket)
        error += (len(bucket) / total) * abs(bucket_accuracy - bucket_confidence)
    return max(0.0, min(1.0, error))


def confidence_reliability_score(outcomes: List[EngineOutcomeRecord], num_bins: int = 10) -> float:
    """`1 - expected_calibration_error` - `1.0` means confidence values
    can be fully trusted as accuracy estimates, `0.0` means they carry
    no useful information."""
    return max(0.0, min(1.0, 1.0 - expected_calibration_error(outcomes, num_bins)))
