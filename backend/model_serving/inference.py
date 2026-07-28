"""
OptiTrade Model Serving Platform — Inference Engine.

Production inference over an already-loaded model (see `loader.py`).
Reuses `ml_training.shadow.adapter.MLModelVotingEngineAdapter` directly
for the actual feature-vector -> `decision_engine.models.EngineVote`
conversion - the exact same adapter Continuous Learning's shadow path
already uses - rather than re-deriving "how do I turn a classifier's
probabilities into a BUY/HOLD/SELL vote" a second time. This is also
what "reuse the existing Decision Engine outputs" means here: a served
model's prediction is structurally identical to any other voting
engine's `EngineVote`, so it can be registered directly into a Pipeline
run (see `service.py`/`pipeline/service.py`) with zero new response
shapes.

Supports every mode requirement 2 asks for:
  - single prediction (`predict_one`)
  - batch prediction (`predict_batch` - sequential, deterministic order)
  - parallel inference (`predict_batch_parallel` - a thread pool, for
    synchronous callers like `Pipeline`/a CLI)
  - async prediction (`predict_async`/`predict_batch_async` - for the
    FastAPI async route)
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from decision_engine.models import EngineVote
from ml_training.config import MLTrainingConfig
from ml_training.features.extractor import FeatureExtractor
from ml_training.shadow.adapter import MLModelVotingEngineAdapter
from model_serving.config import ModelServingConfig
from model_serving.loader import LoadedModel


class InferenceEngine:
    def __init__(
        self,
        feature_extractor: Optional[FeatureExtractor] = None,
        config: Optional[ModelServingConfig] = None,
        ml_training_config: Optional[MLTrainingConfig] = None,
        max_workers: Optional[int] = None,
    ) -> None:
        self.config = config or ModelServingConfig.from_env()
        # `MLModelVotingEngineAdapter` (ml_training.shadow.adapter) takes
        # an `MLTrainingConfig` - a distinct type from this package's own
        # `ModelServingConfig` - for its expected_return_scale_pct/
        # default_expected_volatility_pct fields.
        self.ml_training_config = ml_training_config or MLTrainingConfig.from_env()
        self.feature_extractor = feature_extractor or FeatureExtractor()
        self._pool = ThreadPoolExecutor(max_workers=max_workers or self.config.max_parallel_workers)
        self._adapters: Dict[str, MLModelVotingEngineAdapter] = {}

    def adapter_for(self, loaded_model: LoadedModel) -> MLModelVotingEngineAdapter:
        """Builds (once) and reuses the `MLModelVotingEngineAdapter` for
        a given model_id - rebuilding it every call would be harmless
        but wasteful, since it holds no per-call state."""
        entry = loaded_model.entry
        cached = self._adapters.get(entry.model_id)
        if cached is not None and cached.trainer is loaded_model.prediction_source:
            return cached

        adapter = MLModelVotingEngineAdapter(
            model_id=entry.model_id, engine_version=entry.engine_version,
            trainer=loaded_model.prediction_source, feature_names=entry.feature_list,
            feature_extractor=self.feature_extractor, config=self.ml_training_config,
        )
        self._adapters[entry.model_id] = adapter
        return adapter

    def predict_one(self, loaded_model: LoadedModel, symbol: str) -> EngineVote:
        return self.adapter_for(loaded_model).vote(symbol)

    def predict_batch(self, loaded_model: LoadedModel, symbols: List[str]) -> List[EngineVote]:
        adapter = self.adapter_for(loaded_model)
        return [adapter.vote(symbol) for symbol in symbols]

    def predict_batch_parallel(self, loaded_model: LoadedModel, symbols: List[str]) -> List[EngineVote]:
        adapter = self.adapter_for(loaded_model)
        futures = [self._pool.submit(adapter.vote, symbol) for symbol in symbols]
        return [future.result() for future in futures]

    async def predict_async(self, loaded_model: LoadedModel, symbol: str) -> EngineVote:
        return await asyncio.to_thread(self.predict_one, loaded_model, symbol)

    async def predict_batch_async(self, loaded_model: LoadedModel, symbols: List[str]) -> List[EngineVote]:
        adapter = self.adapter_for(loaded_model)
        return await asyncio.gather(*(asyncio.to_thread(adapter.vote, symbol) for symbol in symbols))

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False)
