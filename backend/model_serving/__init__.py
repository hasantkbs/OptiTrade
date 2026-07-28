"""
OptiTrade Model Serving Platform.

Loads ACTIVE models directly from the Model Registry
(`ml_training.registry`), serves them for production inference, runs
SHADOW models in the background for Continuous Learning only, and folds
served models into the production Pipeline as ordinary voting engines -
see `service.py:PredictionService`, the single top-level entry point.

Unlike `research_lab`/`ml_training`, this package DOES execute during
live production requests - it is the deliberate, sole bridge between
the offline Model Registry and live serving. `tests/test_research_isolation.py`
enforces the resulting one-directional rule: every other production
package (`pipeline`, `main.py`, `decision_engine`, `engine_registry`,
`engines`, `learning`, ...) may depend on `model_serving`, but only
`model_serving` itself may depend on `ml_training` - and, as with every
other production package, it never depends on `research_lab`.
"""
from model_serving.models import MLPredictionRequest, MLPredictionResult, ServingHealthReport
from model_serving.service import PredictionService

__all__ = ["PredictionService", "MLPredictionRequest", "MLPredictionResult", "ServingHealthReport"]
