"""
OptiTrade Pipeline.

The production execution pipeline: Load Features -> Technical Engine ->
Fundamental Engine -> News Engine (the three run in parallel) ->
Decision Engine -> Explanation Engine -> Learning Tracker -> API
Response. Research Lab never executes in this path - see
`tests/test_research_isolation.py`.
"""
from pipeline.models import PipelineResponse, QuantAnalysisRequest
from pipeline.service import PipelineService

__all__ = ["PipelineService", "PipelineResponse", "QuantAnalysisRequest"]
