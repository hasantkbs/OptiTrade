"""
OptiTrade Engine Registry.

Discovers, validates, and executes voting engines
(`decision_engine.interfaces.VotingEngineProtocol`). Distinct from
`decision_engine.registry.VotingEngineRegistry`: this registry validates
interface compatibility on registration, supports multiple versions of
the same engine name, supports enabling/disabling without
unregistering, and returns execution metadata for every run (success,
failure, or disabled).
"""
from engine_registry.discovery import discover_engines
from engine_registry.executor import execute_all, execute_one
from engine_registry.models import ExecutionMetadata, ExecutionStatus
from engine_registry.registry import EngineRegistry, default_registry

__all__ = [
    "EngineRegistry",
    "default_registry",
    "discover_engines",
    "execute_one",
    "execute_all",
    "ExecutionMetadata",
    "ExecutionStatus",
]
