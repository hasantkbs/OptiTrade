"""
OptiTrade Decision Engine.

The single component responsible for investment decisions
(BUY/HOLD/SELL). Aggregates accuracy-weighted votes from every registered
voting engine into one `DecisionOutput`. LLMs never vote and never
influence this aggregation — see `decision_engine.models` and
`docs/architecture/gap-analysis.md` section 2.
"""
from decision_engine.models import DecisionOutput, EngineVote, Prediction
from decision_engine.registry import VotingEngineRegistry
from decision_engine.service import DecisionEngine

__all__ = [
    "DecisionEngine",
    "DecisionOutput",
    "EngineVote",
    "Prediction",
    "VotingEngineRegistry",
]
