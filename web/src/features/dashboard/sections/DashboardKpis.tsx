import { KpiCard } from '../../../components/ui/KpiCard'
import { useOverview, usePortfolioDashboard, usePortfolioList } from '../hooks'
import { apiErrorMessage } from '../../../api/client'
import { ErrorState } from '../../../components/ui/ErrorState'
import styles from '../../../pages/DashboardPage.module.css'

function formatCurrency(value: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 0 }).format(value)
}

/**
 * Top KPI row (WEB STEP 2 §3). Backed by GET /dashboard/overview
 * (dashboard/models.py::OverviewMetrics) plus, when at least one
 * portfolio exists, GET /dashboard/portfolios/{id} for the value/P&L/
 * drawdown cards - every value here is a real field from one of those
 * two responses. Cards with no backing data (no portfolio yet) show an
 * explicit unavailable state instead of a zero or a guess.
 */
export function DashboardKpis() {
  const overview = useOverview()
  const portfolios = usePortfolioList()
  const firstPortfolio = portfolios.data?.[0]
  const portfolioDashboard = usePortfolioDashboard(firstPortfolio?.id ?? undefined)

  if (overview.isError) {
    return <ErrorState message={apiErrorMessage(overview.error)} onRetry={() => void overview.refetch()} />
  }

  if (portfolios.isError) {
    return <ErrorState message={apiErrorMessage(portfolios.error)} onRetry={() => void portfolios.refetch()} />
  }

  const hasPortfolio = Boolean(firstPortfolio)
  const dashboard = portfolioDashboard.data?.dashboard
  const risk = dashboard?.risk

  return (
    <div className={styles.kpiRow}>
      <KpiCard
        label="Portfolio value"
        value={dashboard ? formatCurrency(dashboard.total_value, firstPortfolio!.base_currency) : undefined}
        isLoading={hasPortfolio && portfolioDashboard.isLoading}
        isUnavailable={!hasPortfolio && !portfolios.isLoading}
        unavailableReason={!hasPortfolio ? 'No portfolio yet' : undefined}
        tooltip="Current total value of your first portfolio (cash + positions)."
      />
      <KpiCard
        label="Unrealized P&L"
        value={dashboard ? formatCurrency(dashboard.unrealized_pnl, firstPortfolio!.base_currency) : undefined}
        isLoading={hasPortfolio && portfolioDashboard.isLoading}
        isUnavailable={!hasPortfolio && !portfolios.isLoading}
        unavailableReason={!hasPortfolio ? 'No portfolio yet' : undefined}
        tone={dashboard ? (dashboard.unrealized_pnl >= 0 ? 'positive' : 'negative') : 'neutral'}
        tooltip="Unrealized profit/loss across all open positions."
      />
      <KpiCard
        label="Max drawdown"
        value={risk ? `${risk.max_drawdown_pct.toFixed(1)}%` : undefined}
        isLoading={hasPortfolio && portfolioDashboard.isLoading}
        isUnavailable={hasPortfolio ? !risk && !portfolioDashboard.isLoading : !portfolios.isLoading}
        unavailableReason={!hasPortfolio ? 'No portfolio yet' : !risk ? 'Risk not yet computed' : undefined}
        tone="negative"
        tooltip="Largest peak-to-trough decline observed for this portfolio."
      />
      <KpiCard
        label="Active alerts"
        value={overview.data?.total_alerts}
        isLoading={overview.isLoading}
        tooltip="Alerts currently configured across all your watchlists and portfolios."
      />
      <KpiCard
        label="Watchlists"
        value={overview.data?.total_watchlists}
        isLoading={overview.isLoading}
      />
      <KpiCard
        label="Active engines"
        value={overview.data?.active_engines}
        isLoading={overview.isLoading}
        tooltip="Decision Engine sub-engines (Technical, Fundamental, News) currently contributing to decisions."
      />
    </div>
  )
}
