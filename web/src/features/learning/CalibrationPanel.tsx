import { Badge } from '../../components/ui/Badge'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { SkeletonCard } from '../../components/ui/Skeleton'
import { Tooltip } from '../../components/ui/Tooltip'
import { useEngineDashboard, useLearningDashboard } from '../dashboard/hooks'
import { apiErrorMessage } from '../../api/client'
import type { CalibrationHistoryPoint, RollingWindow } from '../../api/types'
import styles from './CalibrationPanel.module.css'

const WINDOW_ORDER: RollingWindow[] = ['7d', '30d', '90d', 'lifetime']
const WINDOW_LABEL: Record<RollingWindow, string> = { '7d': '7D', '30d': '30D', '90d': '90D', lifetime: 'Lifetime' }

function groupByEngine(points: CalibrationHistoryPoint[]) {
  const groups = new Map<string, CalibrationHistoryPoint[]>()
  for (const point of points) {
    const key = `${point.engine_name}-${point.engine_version}`
    const list = groups.get(key) ?? []
    list.push(point)
    groups.set(key, list)
  }
  return groups
}

/**
 * Two genuinely distinct real calibration signals, kept visually
 * separate: per-engine ECE/reliability across rolling windows (GET
 * /dashboard/learning's `calibration_history`, dashboard/models.py::
 * CalibrationHistoryPoint) and model-level before/after calibration
 * correction (GET /dashboard/engines's `calibration`, dashboard/
 * models.py::CalibrationSnapshot, read from `ml_training_calibration_
 * results`). Only the real scalar ECE is shown - the backend does not
 * return per-bucket reliability data, so no bucket chart is built
 * (WEB STEP 7 §"Calibration").
 */
export function CalibrationPanel() {
  const learning = useLearningDashboard()
  const engines = useEngineDashboard()

  const engineGroups = groupByEngine(learning.data?.calibration_history ?? [])

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Calibration</CardTitle>
          <CardSubtitle>How well stated confidence matches actual accuracy</CardSubtitle>
        </div>
      </CardHeader>

      {learning.isLoading ? <SkeletonCard /> : null}
      {learning.isError ? <ErrorState message={apiErrorMessage(learning.error)} onRetry={() => void learning.refetch()} /> : null}

      {learning.data ? (
        engineGroups.size === 0 ? (
          <EmptyState title="No calibration history yet" description="Appears once engines have accumulated evaluated samples across rolling windows." />
        ) : (
          <div className={styles.engineGrid}>
            {[...engineGroups.entries()].map(([key, points]) => {
              const sorted = WINDOW_ORDER.map((window) => points.find((p) => p.window === window)).filter(Boolean) as CalibrationHistoryPoint[]
              const [engineName, engineVersion] = [sorted[0].engine_name, sorted[0].engine_version]
              return (
                <div key={key} className={styles.engineCard}>
                  <div className={styles.engineHeader}>
                    <span className={styles.engineName}>{engineName}</span>
                    <span className={styles.engineVersion}>v{engineVersion}</span>
                  </div>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th />
                        {sorted.map((p) => (
                          <th key={p.window} className="num">
                            {WINDOW_LABEL[p.window]}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>
                          <Tooltip content="Expected Calibration Error - lower means confidence better matches actual accuracy.">
                            <span>ECE</span>
                          </Tooltip>
                        </td>
                        {sorted.map((p) => (
                          <td key={p.window} className="num">
                            {p.calibration_error.toFixed(3)}
                          </td>
                        ))}
                      </tr>
                      <tr>
                        <td>Reliability</td>
                        {sorted.map((p) => (
                          <td key={p.window} className="num">
                            {p.confidence_reliability.toFixed(3)}
                          </td>
                        ))}
                      </tr>
                    </tbody>
                  </table>
                </div>
              )
            })}
          </div>
        )
      ) : null}

      <div className={styles.modelSection}>
        <span className={styles.sectionLabel}>Model calibration correction</span>

        {engines.isLoading ? <SkeletonCard /> : null}
        {engines.isError ? <ErrorState message={apiErrorMessage(engines.error)} onRetry={() => void engines.refetch()} /> : null}

        {engines.data ? (
          engines.data.calibration.length === 0 ? (
            <EmptyState title="No model calibration results yet" description="Appears once a served model has a recorded calibration correction." />
          ) : (
            <ul className={styles.modelList}>
              {engines.data.calibration.map((snapshot) => {
                const improved = snapshot.calibration_error_after < snapshot.calibration_error_before
                return (
                  <li key={`${snapshot.model_id}-${snapshot.computed_at}`} className={styles.modelRow}>
                    <span className={`num ${styles.modelId}`}>{snapshot.model_id}</span>
                    <span className={styles.method}>{snapshot.method}</span>
                    <span className="num">
                      {snapshot.calibration_error_before.toFixed(3)} → {snapshot.calibration_error_after.toFixed(3)}
                    </span>
                    <Badge tone={improved ? 'positive' : 'neutral'}>{improved ? 'Improved' : 'Unchanged'}</Badge>
                  </li>
                )
              })}
            </ul>
          )
        ) : null}
      </div>
    </Card>
  )
}
