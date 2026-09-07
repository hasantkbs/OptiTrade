import { KpiCard } from '../../components/ui/KpiCard'
import type { Alert } from '../../api/types'
import styles from './AlertsSummary.module.css'

interface AlertsSummaryProps {
  alerts: Alert[]
}

/**
 * Every number here is a plain count over the real GET /alerts response
 * (watchlist/models.py::Alert) - no success rate, accuracy, or average
 * trigger time, since the backend doesn't provide the outcome data
 * those would require (WEB STEP 6 §"Alert summary").
 */
export function AlertsSummary({ alerts }: AlertsSummaryProps) {
  const enabled = alerts.filter((alert) => alert.enabled).length
  const everTriggered = alerts.filter((alert) => alert.last_triggered_at != null).length

  return (
    <div className={styles.row}>
      <KpiCard label="Total alerts" value={alerts.length} />
      <KpiCard label="Enabled" value={enabled} />
      <KpiCard label="Disabled" value={alerts.length - enabled} />
      <KpiCard
        label="Ever triggered"
        value={everTriggered}
        tooltip="Alerts with a real last_triggered_at timestamp from a past scan."
      />
    </div>
  )
}
