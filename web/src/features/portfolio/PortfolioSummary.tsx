import { KpiCard } from '../../components/ui/KpiCard'
import type { PortfolioDashboard } from '../../api/types'
import styles from './PortfolioSummary.module.css'

function formatCurrency(value: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 0 }).format(value)
}

interface PortfolioSummaryProps {
  dashboard: PortfolioDashboard
  sharpeRatio: number | null
  currency: string
}

/**
 * Every card here is a real field from GET /dashboard/portfolios/{id}
 * (portfolio/models.py::PortfolioDashboard +
 * dashboard/portfolio_dashboard.py::PortfolioDashboardExtended.sharpe_ratio) -
 * "Positions" is a real count (dashboard.positions.length), not a
 * separate backend field, so it's not formatted as currency (WEB STEP 3 §4).
 */
export function PortfolioSummary({ dashboard, sharpeRatio, currency }: PortfolioSummaryProps) {
  return (
    <div className={styles.row}>
      <KpiCard label="Total value" value={formatCurrency(dashboard.total_value, currency)} tooltip="Cash plus the current market value of all open positions." />
      <KpiCard
        label="Unrealized P&L"
        value={formatCurrency(dashboard.unrealized_pnl, currency)}
        tone={dashboard.unrealized_pnl >= 0 ? 'positive' : 'negative'}
        tooltip="Paper gain/loss on currently open positions - not yet realized by selling."
      />
      <KpiCard
        label="Realized P&L"
        value={formatCurrency(dashboard.realized_pnl, currency)}
        tone={dashboard.realized_pnl >= 0 ? 'positive' : 'negative'}
        tooltip="Cumulative gain/loss already locked in from closed trades."
      />
      <KpiCard label="Cash balance" value={formatCurrency(dashboard.cash_balance, currency)} />
      <KpiCard label="Open positions" value={dashboard.positions.length} />
      <KpiCard
        label="Sharpe ratio"
        value={sharpeRatio != null ? sharpeRatio.toFixed(2) : undefined}
        isUnavailable={sharpeRatio == null}
        unavailableReason={sharpeRatio == null ? 'Needs more snapshot history' : undefined}
        tooltip="Risk-adjusted return computed from this portfolio's recorded value snapshots. Requires at least two snapshots to compute."
      />
    </div>
  )
}
