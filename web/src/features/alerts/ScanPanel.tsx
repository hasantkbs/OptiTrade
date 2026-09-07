import { Link } from 'react-router-dom'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { ErrorState } from '../../components/ui/ErrorState'
import { apiErrorMessage } from '../../api/client'
import type { AlertSeverity } from '../../api/types'
import { useScanAlerts } from './hooks'
import styles from './ScanPanel.module.css'

const SEVERITY_TONE: Record<AlertSeverity, 'info' | 'warning' | 'negative'> = {
  info: 'info',
  warning: 'warning',
  critical: 'negative',
}

/**
 * Backed by POST /alerts/scan (watchlist/models.py::ScanReport) - an
 * explicit, user-triggered, rate-limited (5/minute) action, never
 * polled automatically. Triggered results shown here are the backend's
 * real `AlertTriggerEvent`s (severity, message, evidence) nested inside
 * the report's `outcomes[]` - not re-derived or guessed. There is no
 * push-notification infrastructure anywhere in this backend
 * (`NotificationPayload`'s own docstring: "never sends it anywhere"),
 * so this only ever shows the result of a scan the user just ran.
 */
export function ScanPanel() {
  const scan = useScanAlerts()
  const report = scan.data

  const triggeredOutcomes = report?.outcomes.filter((outcome) => outcome.trigger_event != null) ?? []
  const statusCounts: Partial<Record<string, number>> = {}
  for (const outcome of report?.outcomes ?? []) {
    statusCounts[outcome.status] = (statusCounts[outcome.status] ?? 0) + 1
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Scan alerts</CardTitle>
          <CardSubtitle>Evaluates your alerts against current market data right now</CardSubtitle>
        </div>
        <Button size="sm" onClick={() => scan.mutate()} isLoading={scan.isPending} disabled={scan.isPending}>
          Scan now
        </Button>
      </CardHeader>

      {scan.isError ? <ErrorState message={apiErrorMessage(scan.error)} onRetry={() => scan.mutate()} /> : null}

      {!scan.isPending && !report && !scan.isError ? (
        <p className={styles.prompt}>This system evaluates alerts on the backend - it does not send push notifications. Run a scan to check now.</p>
      ) : null}

      {report ? (
        <div className={styles.body}>
          <div className={styles.summaryRow}>
            <div className={styles.summaryItem}>
              <span className={styles.label}>Checked</span>
              <span className="num">
                {report.checked_count} / {report.total_alerts}
              </span>
            </div>
            <div className={styles.summaryItem}>
              <span className={styles.label}>Triggered</span>
              <span className="num">{report.triggered_count}</span>
            </div>
            <div className={styles.summaryItem}>
              <span className={styles.label}>Started</span>
              <span>{new Date(report.started_at).toLocaleTimeString()}</span>
            </div>
          </div>

          {triggeredOutcomes.length > 0 ? (
            <div className={styles.section}>
              <span className={styles.sectionLabel}>Triggered</span>
              <ul className={styles.triggeredList}>
                {triggeredOutcomes.map((outcome) => {
                  const event = outcome.trigger_event!
                  return (
                    <li key={outcome.alert_id} className={styles.triggeredItem}>
                      <div className={styles.triggeredHeader}>
                        <Badge tone={SEVERITY_TONE[event.severity]}>{event.severity}</Badge>
                        {event.symbol ? (
                          <Link to={`/assets/${event.symbol}`} className={`num ${styles.triggeredSymbol}`}>
                            {event.symbol}
                          </Link>
                        ) : null}
                        <span className={styles.triggeredTime}>{new Date(event.triggered_at).toLocaleTimeString()}</span>
                      </div>
                      <p className={styles.triggeredMessage}>{event.message}</p>
                      {Object.keys(event.evidence).length > 0 ? (
                        <p className={styles.evidence}>
                          {Object.entries(event.evidence)
                            .map(([key, value]) => `${key}: ${value.toFixed(2)}`)
                            .join(' · ')}
                        </p>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
            </div>
          ) : null}

          <div className={styles.section}>
            <span className={styles.sectionLabel}>All outcomes ({report.outcomes.length})</span>
            <div className={styles.statusChips}>
              {Object.entries(statusCounts).map(([status, count]) => (
                <span key={status} className={styles.statusChip}>
                  {status.replace(/_/g, ' ')}: {count}
                </span>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  )
}
