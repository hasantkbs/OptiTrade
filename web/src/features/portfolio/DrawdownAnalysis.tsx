import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { EmptyState } from '../../components/ui/EmptyState'
import type { RiskAnalytics } from '../../api/types'
import styles from './DrawdownAnalysis.module.css'

interface DrawdownAnalysisProps {
  risk: RiskAnalytics | null
}

/**
 * `max_drawdown_pct` / `expected_drawdown_pct` (portfolio/models.py::
 * RiskAnalytics, both bounded <= 0.0 by the backend model - a negative
 * number IS the correct sign here) are the only drawdown figures the
 * backend computes, and both are single current scalars, not a time
 * series. Same underlying gap as PerformanceHistory: no endpoint reads
 * back historical PortfolioSnapshots, so no drawdown chart is built
 * (WEB STEP 3 §9).
 */
export function DrawdownAnalysis({ risk }: DrawdownAnalysisProps) {
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Drawdown</CardTitle>
          <CardSubtitle>Peak-to-trough decline</CardSubtitle>
        </div>
      </CardHeader>

      {risk ? (
        <div className={styles.scalarRow}>
          <div className={styles.stat}>
            <span className={styles.label}>Max drawdown</span>
            <span className={`num ${styles.value} ${risk.max_drawdown_pct < 0 ? styles.negative : styles.neutral}`}>
              {risk.max_drawdown_pct.toFixed(1)}%
            </span>
          </div>
          <div className={styles.stat}>
            <span className={styles.label}>Expected drawdown</span>
            <span className={`num ${styles.value} ${risk.expected_drawdown_pct < 0 ? styles.negative : styles.neutral}`}>
              {risk.expected_drawdown_pct.toFixed(1)}%
            </span>
          </div>
        </div>
      ) : (
        <p className={styles.value} style={{ marginBottom: 'var(--space-4)' }}>
          Not yet computed for this portfolio.
        </p>
      )}

      <EmptyState
        variant="unavailable"
        title="Historical drawdown not available"
        description="Only a current point-in-time drawdown figure is exposed by the backend - there is no endpoint to read back how it moved over time, so no drawdown chart is shown."
      />
    </Card>
  )
}
