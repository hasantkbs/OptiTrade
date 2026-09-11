"""
OptiTrade Intelligence Primitives.

Reusable, deterministic building blocks derived from an already-final
`decision_engine.models.DecisionOutput` - never a second decision
engine, never a vote, never an LLM call:

- `decision_diff`: compares a symbol's current and previous
  `DecisionOutput` (both read from the Decision Engine's own persisted
  history) and reports what changed.
- `opportunity`: classifies an already-final `DecisionOutput` into a
  product-facing label (STRONG_BUY_BIAS/BUY_BIAS/HOLD/WATCH/
  RISK_DETERIORATING) via explicit, config-driven rules.
- `anomaly`: the canonical `MarketAnomalyDetector` (moved from
  `core.market_anomaly_detector`, which now re-exports this module for
  backward compatibility).
- `market_scanner`: batch-orchestrates the canonical
  `pipeline.PipelineService.run()` across many symbols under bounded
  concurrency and a per-symbol timeout - never a second analysis path.
- `opportunity_ranking`: deterministically orders an already-produced
  `MarketScanResult`'s successful symbols by their `opportunity`
  classification - a presentation layer, never a composite score.
- `portfolio_intelligence`: evaluates an EXISTING portfolio's open
  positions for material decision/risk/opportunity/data-quality changes,
  composing `portfolio.service.PortfolioService`, decision history, and
  the primitives above - decision support only, never a buy/sell
  instruction.
- `watchlist_intelligence`: the watchlist-domain twin of
  `portfolio_intelligence` - evaluates an EXISTING watchlist's symbols
  for the same material decision/risk/opportunity/data-quality changes,
  composing `watchlist.watchlist_service.WatchlistService` instead of
  the Portfolio Intelligence Platform.
- `background_intelligence`: batches `market_scanner.MarketScanner`
  (Phase C) and `opportunity_ranking.rank_opportunities` (Phase D) into
  one bounded, schedulable tick over the existing market symbol
  universe (`core.market_config`) - global market intelligence only,
  meant to be driven by the existing leader-elected scheduler loop in
  `main.py`, never a second scanner/ranking/scheduler implementation.

Nothing in this package votes, scores, overrides a Tier-A decision, or
calls an LLM. `pipeline.PipelineService` + `decision_engine` remain the
only canonical production decision path.
"""
from intelligence.anomaly import MarketAlert, MarketAnomalyDetector
from intelligence.background_intelligence import (
    BackgroundIntelligenceOrchestrator,
    MarketConfigUniverseProvider,
    UniverseProviderProtocol,
)
from intelligence.decision_diff import DecisionHistoryDiffService, diff_decisions, risk_bucket_for_volatility
from intelligence.market_scanner import MarketScanner, PipelineRunnerProtocol
from intelligence.models import (
    BackgroundScanResult,
    BackgroundScanStatus,
    ChangeSignificance,
    DecisionChange,
    MarketScanResult,
    OpportunityAssessment,
    OpportunityLabel,
    OpportunityRankingResult,
    PortfolioFinding,
    PortfolioFindingType,
    PortfolioIntelligenceResult,
    PortfolioIntelligenceSnapshot,
    PositionFinding,
    PositionFindingType,
    RankedOpportunity,
    RankingReason,
    RiskBucket,
    ScanSymbolFailure,
    ScanSymbolResult,
    ScanSymbolStatus,
    WatchlistFinding,
    WatchlistFindingType,
    WatchlistIntelligenceResult,
    WatchlistSymbolSnapshot,
)
from intelligence.opportunity import OpportunityIntelligenceService, classify_opportunity
from intelligence.opportunity_ranking import LABEL_PRIORITY, rank_opportunities, scan_and_rank
from intelligence.portfolio_intelligence import PortfolioIntelligenceService
from intelligence.watchlist_intelligence import WatchlistIntelligenceService

__all__ = [
    "BackgroundIntelligenceOrchestrator",
    "BackgroundScanResult",
    "BackgroundScanStatus",
    "ChangeSignificance",
    "DecisionChange",
    "DecisionHistoryDiffService",
    "LABEL_PRIORITY",
    "MarketAlert",
    "MarketAnomalyDetector",
    "MarketConfigUniverseProvider",
    "MarketScanResult",
    "MarketScanner",
    "OpportunityAssessment",
    "OpportunityIntelligenceService",
    "OpportunityLabel",
    "OpportunityRankingResult",
    "PipelineRunnerProtocol",
    "PortfolioFinding",
    "PortfolioFindingType",
    "PortfolioIntelligenceResult",
    "PortfolioIntelligenceService",
    "PortfolioIntelligenceSnapshot",
    "PositionFinding",
    "PositionFindingType",
    "RankedOpportunity",
    "RankingReason",
    "RiskBucket",
    "ScanSymbolFailure",
    "ScanSymbolResult",
    "ScanSymbolStatus",
    "UniverseProviderProtocol",
    "WatchlistFinding",
    "WatchlistFindingType",
    "WatchlistIntelligenceResult",
    "WatchlistIntelligenceService",
    "WatchlistSymbolSnapshot",
    "classify_opportunity",
    "diff_decisions",
    "rank_opportunities",
    "risk_bucket_for_volatility",
    "scan_and_rank",
]
