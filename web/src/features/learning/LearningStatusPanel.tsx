import { KpiCard } from '../../components/ui/KpiCard'
import { useOverview } from '../dashboard/hooks'
import styles from './LearningStatusPanel.module.css'

/**
 * Backed by GET /dashboard/overview's `learning_status`
 * (dashboard/models.py::LearningStatus) - real counters, no claim of
 * "real-time learning" beyond what these fields actually say
 * (WEB STEP 7 §"Learning status").
 */
export function LearningStatusPanel() {
  const { data, isLoading, isError } = useOverview()
  const status = data?.learning_status

  return (
    <div className={styles.row}>
      <KpiCard label="Engines tracked" value={status?.engines_tracked} isLoading={isLoading} isUnavailable={isError} />
      <KpiCard label="Total samples" value={status?.total_samples} isLoading={isLoading} isUnavailable={isError} />
      <KpiCard label="Pending evaluation" value={status?.pending_samples} isLoading={isLoading} isUnavailable={isError} />
      <KpiCard
        label="Last evaluated"
        value={status?.last_evaluated_at ? new Date(status.last_evaluated_at).toLocaleString() : undefined}
        isLoading={isLoading}
        isUnavailable={isError || (!isLoading && !status?.last_evaluated_at)}
        unavailableReason={!isError && !status?.last_evaluated_at ? 'Not yet evaluated' : undefined}
      />
    </div>
  )
}
