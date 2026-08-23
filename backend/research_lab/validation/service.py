"""
OptiTrade Research Lab — Decision Engine validation: orchestrator.

Reconstructs the live Decision Engine's actual historical track record
purely from already-realized Continuous Learning outcomes - never
re-executes Technical/Fundamental/News, never fetches a hypothetical
historical feature vector, never changes any voting/weighting logic.
This is deliberate: none of those three engines accept an `as_of`
parameter (they always analyze current/live data - see
`engines/{technical,fundamental,news}/engine.py`), so there is no
production-safe way to "replay" them against an arbitrary historical
date without adding a new capability to production engine code, which
this task is explicitly scoped not to do. Validating the system's
*actual* live decisions against their *actual* realized outcomes is the
honest alternative: no fabricated data, no look-ahead risk beyond what
`learning.evaluator.OutcomeEvaluator` (already point-in-time-audited)
already guarantees.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from core.performance_metrics import max_drawdown, sharpe_ratio, sortino_ratio
from learning.models import SampleSource
from learning.persistence import LearningRepository
from paper_trading.config import PaperTradingConfig
from paper_trading.execution import ExecutionEngine
from research_lab.config import ResearchLabConfig
from research_lab.models import SimulatedTrade, ValidationReport
from research_lab.validation import benchmark, metrics
from research_lab.validation.trade_builder import simulate_trade

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


class ValidationService:
    def __init__(
        self,
        learning_repository: Optional[LearningRepository] = None,
        execution_engine: Optional[ExecutionEngine] = None,
        config: Optional[ResearchLabConfig] = None,
        paper_trading_config: Optional[PaperTradingConfig] = None,
        price_fetcher: Optional[benchmark.PriceFetcher] = None,
    ) -> None:
        self.learning_repository = learning_repository or LearningRepository()
        self.config = config or ResearchLabConfig.from_env()
        self.execution_engine = execution_engine or ExecutionEngine(
            config=paper_trading_config or PaperTradingConfig.from_env()
        )
        self.price_fetcher = price_fetcher

    def validate(
        self, symbol: Optional[str] = None, since: Optional[datetime] = None,
        until: Optional[datetime] = None, sample_limit: int = 1000,
    ) -> ValidationReport:
        """The full validation report for every LIVE decision made
        at-or-after `since` (default: the beginning of time) and
        at-or-before `until` (default: now), optionally scoped to one
        `symbol`. Only ever reads already-evaluated samples - a decision
        still awaiting its realized outcome is never included."""
        since = since or _EPOCH
        until = until or datetime.now(timezone.utc)

        samples = self.learning_repository.get_evaluated_samples(SampleSource.LIVE, since=since, limit=sample_limit)
        samples = [s for s in samples if s.decided_at <= until]
        if symbol is not None:
            samples = [s for s in samples if s.symbol == symbol]

        trades: List[SimulatedTrade] = []
        hold_count = 0
        sell_signal_count = 0
        for sample in samples:
            trade = simulate_trade(sample, self.config, self.execution_engine)
            if trade is not None:
                trades.append(trade)
            elif sample.decision.value == "HOLD":
                hold_count += 1
            elif sample.decision.value == "SELL":
                sell_signal_count += 1

        window_start = min((s.decided_at for s in samples), default=since)
        window_end = max((s.decided_at for s in samples), default=until)
        window_days = max((window_end - window_start).total_seconds() / 86400.0, 0.0)

        net_returns = [t.net_return_pct for t in trades]

        report = ValidationReport(
            symbol=symbol,
            window_start=window_start,
            window_end=window_end,
            trade_count=len(trades),
            hold_count=hold_count,
            sell_signal_count=sell_signal_count,
            has_sufficient_samples=len(trades) >= self.config.validation_min_samples_for_report,
            win_rate=metrics.win_rate(trades),
            profit_factor=metrics.profit_factor(trades),
            expectancy_pct=metrics.expectancy_pct(trades),
            sharpe_ratio=sharpe_ratio(net_returns, self.config.risk_free_rate),
            sortino_ratio=sortino_ratio(net_returns, self.config.risk_free_rate),
            max_drawdown=max_drawdown(net_returns),
            exposure_pct=metrics.exposure_pct(trades, window_days),
            equity_curve=metrics.equity_curve(trades),
            monthly_returns=metrics.monthly_returns(trades),
            yearly_returns=metrics.yearly_returns(trades),
            position_size_notional=self.config.validation_position_size_notional,
        )

        benchmark_symbol = self.config.validation_benchmark_symbol
        benchmark_result = benchmark.compute_benchmark(
            benchmark_symbol, window_start, window_end,
            price_fetcher=self.price_fetcher, risk_free_rate=self.config.risk_free_rate,
        )
        if benchmark_result is not None:
            report.benchmark_symbol = benchmark_symbol
            report.benchmark_return_pct, report.benchmark_sharpe_ratio = benchmark_result

        return report
