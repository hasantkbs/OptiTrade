import { Badge } from '../../components/ui/Badge'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { SkeletonCard } from '../../components/ui/Skeleton'
import { useEngineDashboard } from '../dashboard/hooks'
import { apiErrorMessage } from '../../api/client'
import type { DriftSignal } from '../../api/types'
import styles from './SystemEngineStatus.module.css'

const DRIFT_TONE: Record<DriftSignal['drift_type'], 'positive' | 'info' | 'negative' | 'warning'> = {
  improving: 'positive',
  stable: 'info',
  degrading: 'negative',
  unstable: 'warning',
}

/**
 * Decision-focused system context, not a duplicate of the Dashboard's
 * own Engine Intelligence section (which already owns the confidence-
 * history and regime-distribution charts) - just each engine's current
 * live weight and latest drift verdict, both real fields from
 * GET /dashboard/engines (dashboard/models.py::EngineDashboardView),
 * reused via the exact same `useEngineDashboard` hook the Dashboard
 * page uses (WEB STEP 5 §12, no duplicate fetch).
 */
export function SystemEngineStatus() {
  const { data, isLoading, isError, error, refetch } = useEngineDashboard()

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>System engine status</CardTitle>
          <CardSubtitle>Current weight &amp; drift, independent of any single symbol</CardSubtitle>
        </div>
      </CardHeader>

      {isLoading ? <SkeletonCard /> : null}
      {isError ? <ErrorState message={apiErrorMessage(error)} onRetry={() => void refetch()} /> : null}

      {data ? (
        data.engines.length === 0 ? (
          <EmptyState title="No engines reporting yet" description="Engine weight and drift will appear once the Decision Engine has run." />
        ) : (
          <>
            <ul className={styles.list}>
              {data.engines.map((engine) => {
                const weightPct = engine.current_weight != null ? Math.round(engine.current_weight * 100) : null
                return (
                  <li key={`${engine.engine_name}-${engine.engine_version}`} className={styles.row}>
                    <span className={styles.name}>{engine.engine_name}</span>
                    {weightPct != null ? (
                      <>
                        <div className={styles.meterTrack}>
                          <div className={styles.meterFill} style={{ width: `${weightPct}%` }} />
                        </div>
                        <span className={`num ${styles.weightValue}`}>{weightPct}%</span>
                      </>
                    ) : (
                      <span className={styles.unavailable}>Weight unavailable</span>
                    )}
                    {engine.latest_drift ? (
                      <Badge tone={DRIFT_TONE[engine.latest_drift.drift_type]}>{engine.latest_drift.drift_type}</Badge>
                    ) : (
                      <span className={styles.unavailable}>No drift signal</span>
                    )}
                  </li>
                )
              })}
            </ul>
            <p className={styles.generatedAt}>As of {new Date(data.generated_at).toLocaleString()}</p>
          </>
        )
      ) : null}
    </Card>
  )
}
