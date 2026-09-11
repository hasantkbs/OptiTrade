"""OptiTrade Intelligence Primitives — configuration.

Centralizes every threshold used by `intelligence.decision_diff` and
`intelligence.opportunity` so neither module scatters magic numbers of
its own. Nothing here computes a decision or a score - it only decides
how big a change in an already-final `DecisionOutput` counts as
"material", and where a value falls in a risk bucket.

`low_volatility_threshold_pct`/`high_volatility_threshold_pct`
deliberately default to the exact same values as
`pipeline.config.PipelineConfig` (10.0/25.0) so a symbol's risk bucket
means the same thing here as it does in the `/quant/analyze` response
that already reports it (`pipeline.pipeline.Pipeline._risk_level`) -
this is not a second risk engine, just a shared bucketing of a field
the Decision Engine already produces.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class IntelligenceConfig:
    """Runtime settings for the decision-history-diff and
    opportunity-classification primitives."""

    # ── Decision History Diff materiality thresholds ────────────────────
    # A confidence swing smaller than this (both are 0..1 fractions) is
    # noise, not a signal worth surfacing.
    material_confidence_delta: float = 0.15
    # expected_return is in percentage-point units (matches
    # DecisionOutput/EngineVote convention - e.g. 8.0 means "+8%").
    material_expected_return_delta_pct: float = 3.0
    # data_sufficiency is a 0..1 fraction (votes collected / engines available).
    material_data_sufficiency_delta: float = 0.2

    # ── Risk bucketing (mirrors PipelineConfig's volatility thresholds) ─
    low_volatility_threshold_pct: float = 10.0
    high_volatility_threshold_pct: float = 25.0

    # ── Opportunity classification thresholds ───────────────────────────
    # A BUY vote below this confidence is too weak to call a "bias" -
    # WATCH instead.
    watch_confidence_threshold: float = 0.55
    # STRONG_BUY_BIAS requires both high confidence and enough engines
    # actually voting - 0.67 corresponds to "at least 2 of the 3 fixed
    # Technical/Fundamental/News engines contributed" (2/3), the same
    # data_sufficiency semantics pipeline.pipeline._decision_stage
    # already computes (votes collected / engines available).
    strong_buy_confidence_threshold: float = 0.75
    strong_buy_min_data_sufficiency: float = 0.67
    # Below this data_sufficiency, no classification stronger than WATCH
    # is safe regardless of what the (too few) engines that did vote
    # said - 0.34 corresponds to "at least 1 of 3 engines" (1/3).
    min_data_sufficiency_for_classification: float = 0.34

    @classmethod
    def from_env(cls) -> "IntelligenceConfig":
        load_dotenv()
        return cls(
            material_confidence_delta=float(os.getenv("INTELLIGENCE_MATERIAL_CONFIDENCE_DELTA", "0.15")),
            material_expected_return_delta_pct=float(
                os.getenv("INTELLIGENCE_MATERIAL_EXPECTED_RETURN_DELTA_PCT", "3.0")
            ),
            material_data_sufficiency_delta=float(
                os.getenv("INTELLIGENCE_MATERIAL_DATA_SUFFICIENCY_DELTA", "0.2")
            ),
            low_volatility_threshold_pct=float(os.getenv("INTELLIGENCE_LOW_VOLATILITY_THRESHOLD_PCT", "10.0")),
            high_volatility_threshold_pct=float(os.getenv("INTELLIGENCE_HIGH_VOLATILITY_THRESHOLD_PCT", "25.0")),
            watch_confidence_threshold=float(os.getenv("INTELLIGENCE_WATCH_CONFIDENCE_THRESHOLD", "0.55")),
            strong_buy_confidence_threshold=float(
                os.getenv("INTELLIGENCE_STRONG_BUY_CONFIDENCE_THRESHOLD", "0.75")
            ),
            strong_buy_min_data_sufficiency=float(
                os.getenv("INTELLIGENCE_STRONG_BUY_MIN_DATA_SUFFICIENCY", "0.67")
            ),
            min_data_sufficiency_for_classification=float(
                os.getenv("INTELLIGENCE_MIN_DATA_SUFFICIENCY_FOR_CLASSIFICATION", "0.34")
            ),
        )


@dataclass(frozen=True)
class MarketScannerConfig:
    """Runtime settings for `intelligence.market_scanner.MarketScanner`.

    Deliberately separate from `PipelineConfig.max_parallel_workers`/
    `engine_timeout_seconds` - those bound how many *engines* run
    concurrently for one symbol inside a single `PipelineService.run()`
    call; these bound how many *symbols* the scanner runs concurrently,
    each a full `PipelineService.run()` call in its own right. A
    conservative default (3 concurrent full pipeline runs) is chosen
    because each one already fans out its own bounded thread pool
    internally (`ParallelEngineExecutor`) - the scanner's concurrency is
    on top of that, not instead of it.
    """

    max_parallel_symbols: int = 3
    # Generous ceiling for one full PipelineService.run() call (multiple
    # engines with their own retries, plus explanation/learning stages)
    # - not a tuned budget, matching the "generous ceiling, not a tuned
    # budget" convention already used for container resource limits
    # elsewhere in this project.
    symbol_timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "MarketScannerConfig":
        load_dotenv()
        return cls(
            max_parallel_symbols=int(os.getenv("MARKET_SCANNER_MAX_PARALLEL_SYMBOLS", "3")),
            symbol_timeout_seconds=float(os.getenv("MARKET_SCANNER_SYMBOL_TIMEOUT_SECONDS", "30.0")),
        )
