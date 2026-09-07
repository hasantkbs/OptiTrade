import { Card, CardHeader, CardSubtitle, CardTitle } from '../../../components/ui/Card'
import { EmptyState } from '../../../components/ui/EmptyState'
import { ErrorState } from '../../../components/ui/ErrorState'
import { SkeletonCard } from '../../../components/ui/Skeleton'
import { usePortfolioDashboard, usePortfolioList } from '../hooks'
import { apiErrorMessage } from '../../../api/client'
import styles from './PortfolioSummarySection.module.css'

function formatCurrency(value: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 0 }).format(value)
}

/**
 * Backed by GET /portfolios + GET /dashboard/portfolios/{id} (portfolio/models.py::PortfolioDashboard).
 * No historical equity-curve/drawdown time series is exposed by the backend for regular portfolios today
 * (only a single current snapshot + a scalar max_drawdown_pct) - shown as KPIs, not a fabricated chart.
 */
export function PortfolioSummarySection() {
  const portfolios = usePortfolioList()
  const firstPortfolio = portfolios.data?.[0]
  const dashboard = usePortfolioDashboard(firstPortfolio?.id ?? undefined)

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Portfolio</CardTitle>
          <CardSubtitle>{firstPortfolio?.name ?? 'Current snapshot'}</CardSubtitle>
        </div>
      </CardHeader>

      {portfolios.isLoading ? <SkeletonCard /> : null}
      {portfolios.isError ? (
        <ErrorState message={apiErrorMessage(portfolios.error)} onRetry={() => void portfolios.refetch()} />
      ) : null}

      {portfolios.data && portfolios.data.length === 0 ? (
        <EmptyState
          title="No portfolio yet"
          description="Create a portfolio to see its value, P&L, and risk here."
        />
      ) : null}

      {firstPortfolio ? (
        dashboard.isLoading ? (
          <SkeletonCard />
        ) : dashboard.isError ? (
          <ErrorState message={apiErrorMessage(dashboard.error)} onRetry={() => void dashboard.refetch()} />
        ) : dashboard.data ? (
          <div className={styles.grid}>
            <div className={styles.stat}>
              <span className={styles.label}>Total value</span>
              <span className={`num ${styles.value}`}>
                {formatCurrency(dashboard.data.dashboard.total_value, firstPortfolio.base_currency)}
              </span>
            </div>
            <div className={styles.stat}>
              <span className={styles.label}>Unrealized P&amp;L</span>
              <span
                className={`num ${styles.value} ${dashboard.data.dashboard.unrealized_pnl >= 0 ? styles.positive : styles.negative}`}
              >
                {formatCurrency(dashboard.data.dashboard.unrealized_pnl, firstPortfolio.base_currency)}
              </span>
            </div>
            <div className={styles.stat}>
              <span className={styles.label}>Max drawdown</span>
              <span className={`num ${styles.value} ${styles.negative}`}>
                {dashboard.data.dashboard.risk ? `${dashboard.data.dashboard.risk.max_drawdown_pct.toFixed(1)}%` : '—'}
              </span>
            </div>
          </div>
        ) : null
      ) : null}
    </Card>
  )
}
