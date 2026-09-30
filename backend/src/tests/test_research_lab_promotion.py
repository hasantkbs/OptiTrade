"""Tests for research_lab/promotion/. Uses the real PostgreSQL-backed
LearningRepository (via LearningService) and PromotionRepository."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from decision_engine.models import DecisionOutput, EngineVote, Prediction
from learning import accuracy as learning_accuracy
from learning.config import LearningConfig
from learning.evaluator import OutcomeEvaluator
from learning.models import RollingWindow
from learning.persistence import LearningRepository
from learning.service import LearningService
from learning.tracker import SampleTracker
from research_lab.config import ResearchLabConfig
from research_lab.models import PromotionRecommendation
from research_lab.promotion.repository import PromotionRepository
from research_lab.promotion.service import PromotionService

_ENGINE = "PromotionTestEngine"
_SYMBOL = "PROMOX"


def _rising(symbol, start, end):
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    return pd.DataFrame({"Close": [100 + i * 0.5 for i in range(len(dates))]}, index=dates)


def _falling(symbol, start, end):
    dates = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    return pd.DataFrame({"Close": [100 - i * 0.5 for i in range(len(dates))]}, index=dates)


def _track_and_evaluate(repo, version, prediction, price_fetcher, count=25):
    config = LearningConfig(evaluation_horizon_days=5)
    tracker = SampleTracker(repository=repo, config=config)
    evaluator = OutcomeEvaluator(repository=repo, config=config, price_fetcher=price_fetcher)
    decided_at = datetime.now(timezone.utc) - timedelta(days=10)
    for i in range(count):
        vote = EngineVote(
            engine_name=_ENGINE, engine_version=version, prediction=prediction, confidence=0.7,
            expected_return=2.0, volatility=15.0, evidence=["e"], timestamp=decided_at - timedelta(hours=i),
        )
        output = DecisionOutput(
            symbol=_SYMBOL, decision=prediction, confidence=0.7, expected_return=2.0,
            expected_volatility=15.0, aggregation_strategy_version="v1", data_sufficiency=1.0,
            evidence=["e"], engine_results=[vote], timestamp=decided_at - timedelta(hours=i),
        )
        tracker.track_decision(output)
    evaluator.evaluate_pending(now=datetime.now(timezone.utc))

    # PromotionService reads accuracy via LearningService.get_accuracy, which
    # is a read-back of a snapshot LearningScheduler computes and persists -
    # evaluate_pending() alone only marks samples evaluated, so we compute
    # and save that snapshot directly here (mirroring what a learning cycle
    # would do) rather than running the whole scheduler for this test.
    outcomes = repo.get_engine_outcomes(_ENGINE, version, since=datetime.min.replace(tzinfo=timezone.utc))
    metrics = learning_accuracy.compute_accuracy_metrics(_ENGINE, version, RollingWindow.LIFETIME, outcomes)
    repo.save_accuracy_metrics(metrics)


@pytest.fixture
def repos():
    learning_repo = LearningRepository()
    promo_repo = PromotionRepository()
    yield learning_repo, promo_repo
    conn = learning_repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM learning_samples WHERE symbol = %s", (_SYMBOL,))
            cur.execute("DELETE FROM learning_accuracy_metrics WHERE engine_name = %s", (_ENGINE,))
    finally:
        learning_repo._pool.putconn(conn)
    conn2 = promo_repo._pool.getconn()
    try:
        with conn2, conn2.cursor() as cur:
            cur.execute("DELETE FROM research_promotion_decisions WHERE engine_name = %s", (_ENGINE,))
    finally:
        promo_repo._pool.putconn(conn2)


def test_recommend_keep_shadow_when_insufficient_samples(repos):
    learning_repo, promo_repo = repos
    _track_and_evaluate(learning_repo, "v1", Prediction.BUY, _rising, count=3)
    learning_svc = LearningService(repository=learning_repo)
    config = ResearchLabConfig(min_samples_for_promotion_decision=20)
    svc = PromotionService(learning_service=learning_svc, repository=promo_repo, config=config)

    decision = svc.recommend(_ENGINE, "v2", "v1", window=RollingWindow.LIFETIME)
    assert decision.recommendation == PromotionRecommendation.KEEP_SHADOW
    assert "insufficient" in decision.rationale or "needs more" in decision.rationale
    assert decision.id is not None


def test_recommend_promote_when_candidate_clearly_better(repos):
    learning_repo, promo_repo = repos
    # v1 (live): BUY predictions during a FALLING market -> wrong -> low accuracy
    _track_and_evaluate(learning_repo, "v1", Prediction.BUY, _falling, count=25)
    # v2 (candidate): SELL predictions during the SAME falling market -> correct -> high accuracy
    _track_and_evaluate(learning_repo, "v2", Prediction.SELL, _falling, count=25)

    learning_svc = LearningService(repository=learning_repo)
    config = ResearchLabConfig(min_samples_for_promotion_decision=10, promotion_margin=0.05)
    svc = PromotionService(learning_service=learning_svc, repository=promo_repo, config=config)

    decision = svc.recommend(_ENGINE, "v2", "v1", window=RollingWindow.LIFETIME)
    assert decision.recommendation == PromotionRecommendation.PROMOTE
    assert decision.candidate_accuracy > decision.live_accuracy


def test_recommend_reject_when_candidate_clearly_worse(repos):
    learning_repo, promo_repo = repos
    # v1 (live): SELL during falling market -> correct -> high accuracy
    _track_and_evaluate(learning_repo, "v1", Prediction.SELL, _falling, count=25)
    # v2 (candidate): BUY during the SAME falling market -> wrong -> low accuracy
    _track_and_evaluate(learning_repo, "v2", Prediction.BUY, _falling, count=25)

    learning_svc = LearningService(repository=learning_repo)
    config = ResearchLabConfig(min_samples_for_promotion_decision=10, reject_margin=0.05)
    svc = PromotionService(learning_service=learning_svc, repository=promo_repo, config=config)

    decision = svc.recommend(_ENGINE, "v2", "v1", window=RollingWindow.LIFETIME)
    assert decision.recommendation == PromotionRecommendation.REJECT


def test_service_defaults_to_real_dependencies():
    svc = PromotionService()
    assert isinstance(svc.learning_service, LearningService)
    assert isinstance(svc.repository, PromotionRepository)


def test_promotion_repository_list_for_engine(repos):
    learning_repo, promo_repo = repos
    _track_and_evaluate(learning_repo, "v1", Prediction.BUY, _rising, count=3)
    learning_svc = LearningService(repository=learning_repo)
    svc = PromotionService(learning_service=learning_svc, repository=promo_repo)
    svc.recommend(_ENGINE, "v2", "v1", window=RollingWindow.LIFETIME)

    decisions = promo_repo.list_for_engine(_ENGINE, "v2")
    assert len(decisions) >= 1
