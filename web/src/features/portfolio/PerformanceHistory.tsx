import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { EmptyState } from '../../components/ui/EmptyState'
import styles from './PerformanceHistory.module.css'

function formatCurrency(value: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 0 }).format(value)
}

interface PerformanceHistoryProps {
  realizedPnl: number
  unrealizedPnl: number
  sharpeRatio: number | null
  currency: string
}

/**
 * The backend has no read endpoint for historical portfolio value/P&L:
 * `PortfolioService.get_history()` returns `PortfolioSnapshot[]` (a
 * genuine equity-curve shape: as_of/total_value/unrealized_pnl/
 * realized_pnl) and IS used internally by
 * dashboard/portfolio_dashboard.py to compute `sharpe_ratio`, but no
 * `GET /portfolios/{id}/snapshots`-style route exposes that list - only
 * `POST /portfolios/{id}/snapshot` (creates one new point) exists.
 * Calling a mutating endpoint to fake a read, or repeating a single
 * scalar into a chart, would both violate WEB STEP 3 §8's "never
 * fabricate a time series" rule, so this only shows the real current
 * scalars plus an honest unavailable state.
 */
export function PerformanceHistory({ realizedPnl, unrealizedPnl, sharpeRatio, currency }: PerformanceHistoryProps) {
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Performance</CardTitle>
          <CardSubtitle>Current profit &amp; loss</CardSubtitle>
        </div>
      </CardHeader>

      <div className={styles.scalarRow}>
        <div className={styles.stat}>
          <span className={styles.label}>Unrealized P&amp;L</span>
          <span className={`num ${styles.value} ${unrealizedPnl >= 0 ? styles.positive : styles.negative}`}>
            {formatCurrency(unrealizedPnl, currency)}
          </span>
        </div>
        <div className={styles.stat}>
          <span className={styles.label}>Realized P&amp;L</span>
          <span className={`num ${styles.value} ${realizedPnl >= 0 ? styles.positive : styles.negative}`}>
            {formatCurrency(realizedPnl, currency)}
          </span>
        </div>
        <div className={styles.stat}>
          <span className={styles.label}>Sharpe ratio</span>
          <span className={`num ${styles.value}`}>{sharpeRatio != null ? sharpeRatio.toFixed(2) : '—'}</span>
        </div>
      </div>

      <EmptyState
        variant="unavailable"
        title="Historical performance not available"
        description="The backend doesn't currently expose a way to read this portfolio's value over time - only the current snapshot above. This section will show a real performance chart once a historical endpoint exists."
      />
    </Card>
  )
}
