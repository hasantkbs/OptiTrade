"""
OptiTrade Research Lab — backtest orchestrator.

Dispatches to the right fold-splitter (`splitters.py`) for the
requested `BacktestMethod`, computes each fold's metrics by reusing
`research_lab.model_analysis.metrics` (never re-implementing Sharpe/
Sortino/drawdown a second time), and aggregates across every fold's
combined test returns.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from research_lab.backtesting import splitters
from research_lab.config import ResearchLabConfig
from research_lab.model_analysis import metrics
from research_lab.models import BacktestMethod, BacktestResult, FoldResult

Series = List[Tuple[datetime, float]]

_SPLITTERS = {
    BacktestMethod.WALK_FORWARD: lambda series, config: splitters.walk_forward_splits(
        series, config.walk_forward_train_window_days, config.walk_forward_test_window_days,
    ),
    BacktestMethod.ROLLING_WINDOW: lambda series, config: splitters.rolling_window_splits(
        series, config.rolling_window_days, config.rolling_window_step_days,
    ),
    BacktestMethod.PURGED_CV: lambda series, config: splitters.purged_cv_splits(
        series, config.purged_cv_n_folds, config.purge_embargo_days,
    ),
    BacktestMethod.STRESS_TEST: lambda series, config: splitters.stress_test_scenarios(
        series, config.stress_test_shock_pct,
    ),
    BacktestMethod.OUT_OF_SAMPLE: lambda series, config: splitters.out_of_sample_split(
        series, config.out_of_sample_ratio,
    ),
}


class BacktestEngine:
    """Pure computation over an already-fetched chronological return
    series - has no data-access dependency of its own (that's
    `service.py`'s job), so it is trivially testable with synthetic
    series."""

    def __init__(self, config: Optional[ResearchLabConfig] = None) -> None:
        self.config = config or ResearchLabConfig.from_env()

    def run(
        self,
        method: BacktestMethod,
        engine_name: str,
        engine_version: str,
        series: Series,
        symbol: Optional[str] = None,
        experiment_id: Optional[int] = None,
    ) -> BacktestResult:
        sorted_series = sorted(series, key=lambda pair: pair[0])
        folds = _SPLITTERS[method](sorted_series, self.config)

        fold_results: List[FoldResult] = []
        all_test_returns: List[float] = []

        for fold in folds:
            returns = [value for _, value in fold.test_series]
            if len(returns) < self.config.min_samples_for_backtest_fold:
                continue
            fold_results.append(
                FoldResult(
                    fold_index=fold.fold_index, test_start=fold.test_start, test_end=fold.test_end,
                    sample_count=len(returns), total_return=float(sum(returns)),
                    sharpe_ratio=metrics.sharpe_ratio(returns, self.config.risk_free_rate),
                    sortino_ratio=metrics.sortino_ratio(returns, self.config.risk_free_rate),
                    max_drawdown=metrics.max_drawdown(returns),
                    win_rate=sum(1 for value in returns if value > 0) / len(returns),
                    expected_value=metrics.expected_value(returns),
                )
            )
            all_test_returns.extend(returns)

        window_start = sorted_series[0][0] if sorted_series else datetime.now(timezone.utc)
        window_end = sorted_series[-1][0] if sorted_series else datetime.now(timezone.utc)
        win_rate = (
            sum(1 for value in all_test_returns if value > 0) / len(all_test_returns)
            if all_test_returns else 0.0
        )

        return BacktestResult(
            experiment_id=experiment_id, method=method, engine_name=engine_name, engine_version=engine_version,
            symbol=symbol, window_start=window_start, window_end=window_end, folds=fold_results,
            aggregate_sharpe=metrics.sharpe_ratio(all_test_returns, self.config.risk_free_rate),
            aggregate_sortino=metrics.sortino_ratio(all_test_returns, self.config.risk_free_rate),
            aggregate_max_drawdown=metrics.max_drawdown(all_test_returns),
            aggregate_win_rate=win_rate,
            aggregate_expected_value=metrics.expected_value(all_test_returns),
            sample_count=len(all_test_returns),
        )
