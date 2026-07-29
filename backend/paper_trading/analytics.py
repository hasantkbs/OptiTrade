"""
OptiTrade Paper Trading & Trade Journal Platform — analytics.

Round trips are matched FIFO, oldest open BUY lot first, straight from
this package's own `Fill` records (never from the real Portfolio
ledger's replayed transactions - that ledger doesn't track per-lot cost
the way a trade journal needs to). Shorting is not possible (the
underlying `portfolio.PortfolioService.sell` already rejects selling
more than is held), so every closed trade is a BUY-then-SELL pair.
"""
from __future__ import annotations

import statistics
from collections import defaultdict, deque
from typing import Dict, List, Optional, Tuple

from paper_trading.models import (
    AnalyticsSummary,
    ClosedTrade,
    EquityPoint,
    Fill,
    MonthlyPerformance,
    OrderSide,
    PaperAccount,
)


def match_closed_trades(account: PaperAccount, fills: List[Fill]) -> List[ClosedTrade]:
    by_symbol: Dict[str, List[Fill]] = defaultdict(list)
    for fill in fills:
        by_symbol[fill.symbol].append(fill)

    closed_trades: List[ClosedTrade] = []
    for symbol, symbol_fills in by_symbol.items():
        open_lots: deque = deque()  # each: [remaining_qty, price, time, commission_per_unit, tax_per_unit]
        for fill in sorted(symbol_fills, key=lambda f: f.executed_at):
            if fill.side == OrderSide.BUY:
                open_lots.append([
                    fill.quantity, fill.price, fill.executed_at,
                    fill.commission / fill.quantity, fill.tax / fill.quantity,
                ])
                continue

            remaining_to_close = fill.quantity
            sell_commission_per_unit = fill.commission / fill.quantity
            sell_tax_per_unit = fill.tax / fill.quantity
            while remaining_to_close > 1e-9 and open_lots:
                lot = open_lots[0]
                matched_qty = min(lot[0], remaining_to_close)
                gross_pnl = (fill.price - lot[1]) * matched_qty
                commission = matched_qty * (lot[3] + sell_commission_per_unit)
                tax = matched_qty * (lot[4] + sell_tax_per_unit)
                closed_trades.append(
                    ClosedTrade(
                        account_id=account.id, symbol=symbol, side=OrderSide.SELL, quantity=matched_qty,
                        entry_price=lot[1], exit_price=fill.price, entry_time=lot[2], exit_time=fill.executed_at,
                        commission=commission, tax=tax, gross_pnl=gross_pnl, net_pnl=gross_pnl - commission - tax,
                        holding_seconds=(fill.executed_at - lot[2]).total_seconds(),
                    )
                )
                lot[0] -= matched_qty
                remaining_to_close -= matched_qty
                if lot[0] <= 1e-9:
                    open_lots.popleft()

    closed_trades.sort(key=lambda trade: trade.exit_time)
    return closed_trades


def build_equity_curve(account: PaperAccount, closed_trades: List[ClosedTrade]) -> List[EquityPoint]:
    equity = account.starting_balance
    curve = [EquityPoint(as_of=closed_trades[0].entry_time, equity=equity)] if closed_trades else []
    for trade in closed_trades:
        equity += trade.net_pnl
        curve.append(EquityPoint(as_of=trade.exit_time, equity=equity))
    return curve


def compute_max_drawdown(equity_curve: List[EquityPoint]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0].equity
    max_dd = 0.0
    for point in equity_curve:
        peak = max(peak, point.equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - point.equity) / peak)
    return max_dd


def _trade_returns(closed_trades: List[ClosedTrade]) -> List[float]:
    returns = []
    for trade in closed_trades:
        notional = trade.entry_price * trade.quantity
        if notional > 0:
            returns.append(trade.net_pnl / notional)
    return returns


def compute_sharpe_ratio(closed_trades: List[ClosedTrade]) -> Optional[float]:
    returns = _trade_returns(closed_trades)
    if len(returns) < 2:
        return None
    stdev = statistics.stdev(returns)
    if stdev == 0:
        return None
    return statistics.mean(returns) / stdev


def compute_sortino_ratio(closed_trades: List[ClosedTrade]) -> Optional[float]:
    returns = _trade_returns(closed_trades)
    if len(returns) < 2:
        return None
    downside = [r for r in returns if r < 0]
    if not downside:
        return None
    downside_deviation = statistics.pstdev(downside) if len(downside) > 1 else abs(downside[0])
    if downside_deviation == 0:
        return None
    return statistics.mean(returns) / downside_deviation


def compute_profit_factor(closed_trades: List[ClosedTrade]) -> Optional[float]:
    gross_profit = sum(trade.net_pnl for trade in closed_trades if trade.net_pnl > 0)
    gross_loss = abs(sum(trade.net_pnl for trade in closed_trades if trade.net_pnl < 0))
    if gross_loss == 0:
        return None
    return gross_profit / gross_loss


def summarize(account: PaperAccount, closed_trades: List[ClosedTrade]) -> AnalyticsSummary:
    total_trades = len(closed_trades)
    if total_trades == 0:
        return AnalyticsSummary(
            total_trades=0, win_rate=0.0, max_drawdown=0.0, average_holding_time_seconds=0.0, expectancy=0.0,
        )

    wins = [trade for trade in closed_trades if trade.net_pnl > 0]
    equity_curve = build_equity_curve(account, closed_trades)
    net_pnls = [trade.net_pnl for trade in closed_trades]
    best_trade = max(closed_trades, key=lambda trade: trade.net_pnl)
    worst_trade = min(closed_trades, key=lambda trade: trade.net_pnl)

    return AnalyticsSummary(
        total_trades=total_trades,
        win_rate=len(wins) / total_trades,
        profit_factor=compute_profit_factor(closed_trades),
        sharpe_ratio=compute_sharpe_ratio(closed_trades),
        sortino_ratio=compute_sortino_ratio(closed_trades),
        max_drawdown=compute_max_drawdown(equity_curve),
        average_holding_time_seconds=statistics.mean(trade.holding_seconds for trade in closed_trades),
        expectancy=statistics.mean(net_pnls),
        best_trade=best_trade,
        worst_trade=worst_trade,
    )


def monthly_performance(closed_trades: List[ClosedTrade]) -> List[MonthlyPerformance]:
    buckets: Dict[Tuple[int, int], List[ClosedTrade]] = defaultdict(list)
    for trade in closed_trades:
        buckets[(trade.exit_time.year, trade.exit_time.month)].append(trade)

    performance = []
    for (year, month), trades in sorted(buckets.items()):
        wins = [trade for trade in trades if trade.net_pnl > 0]
        performance.append(
            MonthlyPerformance(
                year=year, month=month, net_pnl=sum(trade.net_pnl for trade in trades), trades=len(trades),
                win_rate=len(wins) / len(trades),
            )
        )
    return performance


class AnalyticsService:
    """Facade combining FIFO trade matching with the summary statistics
    above - the entry point `service.py`/FastAPI endpoints should use."""

    def __init__(self, repository) -> None:
        self._repository = repository

    def get_closed_trades(self, account: PaperAccount, symbol: Optional[str] = None) -> List[ClosedTrade]:
        fills = self._repository.list_fills(account.id, symbol=symbol)
        return match_closed_trades(account, fills)

    def get_summary(self, account: PaperAccount, symbol: Optional[str] = None) -> AnalyticsSummary:
        return summarize(account, self.get_closed_trades(account, symbol=symbol))

    def get_equity_curve(self, account: PaperAccount) -> List[EquityPoint]:
        return build_equity_curve(account, self.get_closed_trades(account))

    def get_monthly_performance(self, account: PaperAccount) -> List[MonthlyPerformance]:
        return monthly_performance(self.get_closed_trades(account))
