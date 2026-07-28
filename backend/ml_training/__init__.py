"""
OptiTrade ML Training Platform.

Builds point-in-time-correct, leakage-free training datasets directly
from the Feature Store; trains LightGBM/XGBoost/CatBoost/Random Forest
models behind one uniform interface; optimizes hyperparameters with
Optuna; evaluates, calibrates, and computes feature importance; tracks
every model version through a human-approved promotion lifecycle
(CANDIDATE -> SHADOW -> ACTIVE, or -> ARCHIVED); and deploys shadow
models as ordinary voting engines so Continuous Learning observes them
exactly like Technical/Fundamental/News. Every training run also
produces a Research Lab experiment, benchmark, hypothesis result, and
report - see `ml_training.service.MLTrainingService`, the single
top-level entry point.

This platform never executes during a live production request - see
`tests/test_research_isolation.py`, which guards every production
package from ever importing it, the same way it guards `research_lab`.
"""
from ml_training.service import MLTrainingService

__all__ = ["MLTrainingService"]
