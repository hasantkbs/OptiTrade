"""
OptiTrade Pipeline — per-request execution context.

A plain, mutable carrier threaded through one `Pipeline.run()` call -
not a serialized API model (see `models.py` for those). Accumulates
timing and intermediate results as each stage completes so
`pipeline.py` can build the final `PipelineMetadata` without every
stage needing to know about every other stage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from decision_engine.interfaces import VotingEngineProtocol
from decision_engine.models import DecisionOutput
from explanation_engine.models import Explanation
from pipeline.models import EngineExecutionResult


@dataclass
class PipelineContext:
    symbol: str
    # The engine composition for THIS call only - see pipeline.py's
    # `run()`. Carried here (per-request local state) rather than read
    # from `Pipeline.engines` (shared singleton instance state) so two
    # concurrent `run()` calls with different engine lists - e.g.
    # different ACTIVE model_serving engines resolved a moment apart -
    # can never observe or clobber each other's engine list.
    engines: List[VotingEngineProtocol] = field(default_factory=list)
    stage_durations_ms: Dict[str, float] = field(default_factory=dict)
    execution_results: List[EngineExecutionResult] = field(default_factory=list)
    decision_output: Optional[DecisionOutput] = None
    explanation: Optional[Explanation] = None

    def record_stage(self, name: str, duration_ms: float) -> None:
        self.stage_durations_ms[name] = duration_ms
