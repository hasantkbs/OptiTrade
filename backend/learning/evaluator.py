"""
OptiTrade Continuous Learning — outcome evaluator.

Finds every pending sample whose `evaluation_horizon_days` has elapsed,
looks up the actual price move over that window (via the new,
purely-additive `data.fetcher.fetch_price_history_range`), and persists
the actual return/volatility plus per-prediction directional
correctness. A sample with no price data available yet (e.g. a
newly-listed symbol, or a data-provider gap) is simply left unevaluated
and retried on the next call - never marked evaluated with a fabricated
outcome.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional, Tuple

import pandas as pd

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from data.fetcher import fetch_price_history_range
from decision_engine.models import Prediction
from learning.config import LearningConfig
from learning.models import LearningSample
from learning.persistence import LearningRepository

logger = logging.getLogger(__name__)

PriceFetcher = Callable[[str, datetime, datetime], Optional[pd.DataFrame]]

_LOOKAHEAD_BUFFER_DAYS = 5


class OutcomeEvaluator:
    """Compares pending learning samples against the actual market
    outcome. Never predicts anything itself - purely reads realized
    price history."""

    def __init__(
        self,
        repository: Optional[LearningRepository] = None,
        config: Optional[LearningConfig] = None,
        price_fetcher: Optional[PriceFetcher] = None,
    ) -> None:
        self.repository = repository or LearningRepository()
        self.config = config or LearningConfig.from_env()
        self._price_fetcher: PriceFetcher = price_fetcher or fetch_price_history_range

    def evaluate_pending(self, now: Optional[datetime] = None) -> int:
        """Evaluates every pending sample whose horizon has elapsed as
        of `now`. Returns how many samples were newly evaluated.

        Each sample is isolated - a malformed sample or a price-fetch/
        persistence failure for one sample is logged and skipped rather
        than aborting the rest of the batch (matches the graceful-
        degradation convention `pipeline.pipeline.Pipeline` already uses
        for its own per-stage/per-vote external calls)."""
        started_at = time.perf_counter()
        now = now or datetime.now(timezone.utc)
        pending = self.repository.get_pending_samples(now, limit=self.config.evaluation_batch_size)

        evaluated_count = 0
        failed_count = 0
        for sample in pending:
            try:
                if self._evaluate_one(sample, now):
                    evaluated_count += 1
            except Exception as exc:
                failed_count += 1
                log_event(
                    logger, component="learning", module="learning.evaluator", operation="evaluate_one",
                    status=STATUS_ERROR, sample_id=sample.id, symbol=sample.symbol,
                    error_type=type(exc).__name__, level=logging.ERROR,
                )

        log_event(
            logger, component="learning", module="learning.evaluator", operation="evaluate_pending",
            status=STATUS_SUCCESS, pending_count=len(pending), evaluated_count=evaluated_count,
            failed_count=failed_count, execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return evaluated_count

    def _evaluate_one(self, sample: LearningSample, now: datetime) -> bool:
        outcome = self._compute_outcome(sample)
        if outcome is None:
            return False
        actual_return, actual_volatility = outcome

        correct = self._is_correct(sample.decision, actual_return)
        self.repository.mark_sample_evaluated(sample.id, actual_return, actual_volatility, correct, now)

        per_engine_correct: List[Tuple[str, str, bool]] = [
            (vote.engine_name, vote.engine_version, self._is_correct(vote.prediction, actual_return))
            for vote in sample.engine_results
        ]
        self.repository.mark_engine_outcomes_evaluated(
            sample.id, actual_return, actual_volatility, per_engine_correct, now,
        )
        return True

    def _compute_outcome(self, sample: LearningSample) -> Optional[Tuple[float, float]]:
        start = sample.decided_at
        horizon_end = sample.decided_at + timedelta(days=sample.evaluation_horizon_days)
        fetch_start = start - timedelta(days=1)
        fetch_end = horizon_end + timedelta(days=_LOOKAHEAD_BUFFER_DAYS)

        history = self._price_fetcher(sample.symbol, fetch_start, fetch_end)
        if history is None or history.empty:
            return None

        start_price = self._price_on_or_after(history, start)
        end_price = self._price_on_or_after(history, horizon_end)
        if start_price is None or end_price is None or start_price == 0:
            return None

        actual_return = (end_price - start_price) / start_price * 100
        actual_volatility = self._realized_volatility(history, start, horizon_end)
        return actual_return, actual_volatility

    @staticmethod
    def _price_on_or_after(history: pd.DataFrame, target: datetime) -> Optional[float]:
        for timestamp, row in history.iterrows():
            ts = timestamp if timestamp.tzinfo is not None else timestamp.replace(tzinfo=timezone.utc)
            if ts >= target:
                return float(row["Close"])
        return None

    @staticmethod
    def _realized_volatility(history: pd.DataFrame, start: datetime, end: datetime) -> float:
        mask = [
            (ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)) >= start
            and (ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)) <= end
            for ts in history.index
        ]
        window = history.loc[mask]
        if len(window) < 2:
            return 0.0
        daily_returns = window["Close"].pct_change().dropna()
        if len(daily_returns) < 2:
            # A single return has no defined sample standard deviation
            # (pandas' default ddof=1 divides by n-1=0, producing NaN) -
            # treat it the same as "insufficient data" rather than
            # propagate a NaN volatility.
            return 0.0
        return float(daily_returns.std() * (252 ** 0.5) * 100)

    def _is_correct(self, prediction: Prediction, actual_return: float) -> bool:
        half_band = self.config.hold_band_pct / 2
        if prediction == Prediction.BUY:
            return actual_return > half_band
        if prediction == Prediction.SELL:
            return actual_return < -half_band
        return abs(actual_return) <= half_band
