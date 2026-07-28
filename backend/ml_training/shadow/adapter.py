"""
OptiTrade ML Training Platform — shadow voting-engine adapter.

Wraps one trained `BaseTrainer` (a fitted direction classifier) as a
`decision_engine.interfaces.VotingEngineProtocol`-compatible voting
engine, so it can be registered into `engine_registry` and observed by
Continuous Learning exactly like Technical/Fundamental/News - see
`shadow/service.py`. This adapter is NEVER registered into a live
`DecisionEngine`'s own registry; it only ever runs through
`research_lab.shadow.service.ShadowEvaluationService.run_shadow_pass`,
which is what makes it "shadow" rather than "live".

`expected_return`/`volatility` have no natural per-vote magnitude for a
raw classifier - the exact situation `engines.fundamental.engine.
FundamentalEngine._expected_volatility` already solves for fundamentals
with no natural per-period volatility measure. The same fallback shape
is used here: the model's own class-probability spread (P(BUY) -
P(SELL), directly analogous to Fundamental's confidence-weighted net
signal) scaled by `config.expected_return_scale_pct`, and a configured
constant volatility since a classifier has no analogous instability
proxy at all.
"""
from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np

from core.structured_logging import STATUS_SUCCESS, log_event
from decision_engine.models import EngineVote, Prediction
from ml_training.config import MLTrainingConfig
from ml_training.features.extractor import FeatureExtractor
from ml_training.training.base import BaseTrainer

logger = logging.getLogger(__name__)


class MLModelVotingEngineAdapter:
    """Satisfies `decision_engine.interfaces.VotingEngineProtocol` via
    `vote()`. `trainer` must already be fitted on a classification
    `direction` label (`trainer.classes_` must be BUY/HOLD/SELL
    strings)."""

    def __init__(
        self,
        model_id: str,
        engine_version: str,
        trainer: BaseTrainer,
        feature_names: List[str],
        feature_extractor: Optional[FeatureExtractor] = None,
        config: Optional[MLTrainingConfig] = None,
    ) -> None:
        if trainer.classes_ is None:
            raise ValueError(
                f"model {model_id!r}: MLModelVotingEngineAdapter requires a fitted classification "
                f"trainer (trainer.classes_ is None)"
            )
        self.model_id = model_id
        self.engine_name = f"MLModel:{model_id}"
        self.engine_version = engine_version
        self.trainer = trainer
        self.feature_names = list(feature_names)
        self.feature_extractor = feature_extractor or FeatureExtractor()
        self.config = config or MLTrainingConfig()

    def vote(self, symbol: str) -> EngineVote:
        feature_vector = self.feature_extractor.extract(symbol)
        X = np.array([[feature_vector.values.get(name, 0.0) for name in self.feature_names]])

        proba = self.trainer.predict_proba(X)[0]
        classes = self.trainer.classes_
        proba_by_class = dict(zip(classes, proba))

        best_index = int(np.argmax(proba))
        prediction = Prediction(classes[best_index])
        confidence = float(proba[best_index])

        p_buy = proba_by_class.get(Prediction.BUY.value, 0.0)
        p_sell = proba_by_class.get(Prediction.SELL.value, 0.0)
        net_signal = p_buy - p_sell
        expected_return = net_signal * self.config.expected_return_scale_pct
        expected_volatility = self.config.default_expected_volatility_pct

        evidence = [f"model_id={self.model_id}", f"algorithm={self.trainer.algorithm.value}"]

        vote = EngineVote(
            engine_name=self.engine_name, engine_version=self.engine_version, prediction=prediction,
            confidence=confidence, expected_return=expected_return, volatility=expected_volatility,
            evidence=evidence,
        )
        log_event(
            logger, component="ml_training", module="ml_training.shadow.adapter", operation="vote",
            status=STATUS_SUCCESS, model_id=self.model_id, symbol=symbol, prediction=prediction.value,
            confidence=confidence,
        )
        return vote
