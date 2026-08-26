"""
OptiTrade ML Training Platform — Shadow Models.

Wraps a trained model as a voting engine (`adapter.py`) and deploys it
into `engine_registry` in shadow mode only (`service.py`), so Continuous
Learning observes its votes exactly like any other engine without it
ever influencing a live decision. No automatic promotion - see
`ml_training.registry` for the human-approved promotion workflow.
"""
from ml_training.shadow.adapter import MLModelVotingEngineAdapter
from ml_training.shadow.service import MLShadowService

__all__ = ["MLModelVotingEngineAdapter", "MLShadowService"]
