"""
OptiTrade Pipeline.

The production execution pipeline: Load Features -> Technical Engine ->
Fundamental Engine -> News Engine -> every currently-served ML model
(`model_serving`, requirement 9 of the Model Serving Platform) - all
run in parallel -> Decision Engine -> Explanation Engine -> Learning
Tracker -> API Response. Research Lab never executes in this path - see
`tests/test_research_isolation.py`. `ml_training` executes only
indirectly, through `model_serving` - the sole bridge between the
offline Model Registry and this live path.
"""
from pipeline.models import PipelineResponse, QuantAnalysisRequest
from pipeline.service import PipelineService

__all__ = ["PipelineService", "PipelineResponse", "QuantAnalysisRequest"]
