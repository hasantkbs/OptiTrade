import { Badge } from '../../components/ui/Badge'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { SkeletonCard } from '../../components/ui/Skeleton'
import { useEngineDashboard, useLearningDashboard } from '../dashboard/hooks'
import { apiErrorMessage } from '../../api/client'
import type { DriftType } from '../../api/types'
import styles from './DriftAlertsPanel.module.css'

const DRIFT_TONE: Record<DriftType, 'positive' | 'info' | 'negative' | 'warning'> = {
  improving: 'positive',
  stable: 'info',
  degrading: 'negative',
  unstable: 'warning',
}

/**
 * `drift_alerts` (GET /dashboard/learning) is already filtered by the
 * backend to only DEGRADING/UNSTABLE signals (dashboard/
 * learning_dashboard.py::_DRIFT_ALERT_TYPES) - a real, backend-decided
 * "needs attention" list, not a frontend filter. The per-engine status
 * row below it (GET /dashboard/engines's `latest_drift`) is what makes
 * "stable" (a real signal: drift monitored, none found) distinguishable
 * from "No drift signal yet" (genuinely never computed) - never
 * collapsed into the same state (WEB STEP 7 §"Drift").
 */
export function DriftAlertsPanel() {
  const learning = useLearningDashboard()
  const engines = useEngineDashboard()
  const alerts = learning.data?.drift_alerts ?? []

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Drift</CardTitle>
          <CardSubtitle>Active alerts and per-engine status</CardSubtitle>
        </div>
      </CardHeader>

      {learning.isLoading ? <SkeletonCard /> : null}
      {learning.isError ? <ErrorState message={apiErrorMessage(learning.error)} onRetry={() => void learning.refetch()} /> : null}

      {learning.data ? (
        alerts.length === 0 ? (
          <EmptyState title="No active drift alerts" description="No engine is currently flagged degrading or unstable." />
        ) : (
          <ul className={styles.alertList}>
            {alerts.map((signal) => (
              <li key={`${signal.engine_name}-${signal.engine_version}-${signal.detected_at}`} className={styles.alertItem}>
                <div className={styles.alertHeader}>
                  <Badge tone={DRIFT_TONE[signal.drift_type]}>{signal.drift_type}</Badge>
                  <span className={styles.engineName}>
                    {signal.engine_name} <span className={styles.engineVersion}>v{signal.engine_version}</span>
                  </span>
                  <span className={styles.detectedAt}>{new Date(signal.detected_at).toLocaleString()}</span>
                </div>
                <p className={styles.evidence}>{signal.evidence}</p>
                <p className={styles.windows}>
                  magnitude <span className="num">{signal.magnitude.toFixed(3)}</span> · recent {signal.recent_window} vs baseline{' '}
                  {signal.baseline_window}
                </p>
              </li>
            ))}
          </ul>
        )
      ) : null}

      <div className={styles.statusSection}>
        <span className={styles.sectionLabel}>Per-engine status</span>
        {engines.isLoading ? <SkeletonCard /> : null}
        {engines.isError ? <ErrorState message={apiErrorMessage(engines.error)} onRetry={() => void engines.refetch()} /> : null}
        {engines.data ? (
          <ul className={styles.statusList}>
            {engines.data.engines.map((engine) => (
              <li key={`${engine.engine_name}-${engine.engine_version}`} className={styles.statusRow}>
                <span>{engine.engine_name}</span>
                {engine.latest_drift ? (
                  <Badge tone={DRIFT_TONE[engine.latest_drift.drift_type]}>{engine.latest_drift.drift_type}</Badge>
                ) : (
                  <span className={styles.unavailable}>No drift signal yet</span>
                )}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </Card>
  )
}
