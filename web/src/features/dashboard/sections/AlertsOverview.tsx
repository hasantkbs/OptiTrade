import { Link } from 'react-router-dom'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../../components/ui/Card'
import { Badge } from '../../../components/ui/Badge'
import { EmptyState } from '../../../components/ui/EmptyState'
import { ErrorState } from '../../../components/ui/ErrorState'
import { SkeletonCard } from '../../../components/ui/Skeleton'
import { useAlertDashboard, useAlerts } from '../hooks'
import { apiErrorMessage } from '../../../api/client'
import styles from './AlertsOverview.module.css'

/**
 * Backed by GET /dashboard/alerts (recently fired trigger events) and
 * GET /alerts (configured Alert records, watchlist/models.py::Alert).
 * `parameters` is the only threshold/value data the backend exposes -
 * shown verbatim as key/value chips. `AlertTriggerEvent.severity`
 * exists in the backend model but is never surfaced by
 * TriggerEventSnapshot, so no severity is invented here (WEB STEP 2 §8).
 */
export function AlertsOverview() {
  const dashboard = useAlertDashboard()
  const configured = useAlerts()

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Alerts</CardTitle>
          <CardSubtitle>{dashboard.data ? `${dashboard.data.fired_last_24h} fired in the last 24h` : 'Last 24 hours'}</CardSubtitle>
        </div>
        <Link to="/alerts" className={styles.viewAll}>
          View all →
        </Link>
      </CardHeader>

      {dashboard.isLoading ? <SkeletonCard /> : null}
      {dashboard.isError ? (
        <ErrorState message={apiErrorMessage(dashboard.error)} onRetry={() => void dashboard.refetch()} />
      ) : null}

      {dashboard.data ? (
        dashboard.data.recently_fired.length === 0 ? (
          <EmptyState title="No alerts fired recently" description="Triggered alerts will appear here as they fire." />
        ) : (
          <ul className={styles.firedList}>
            {dashboard.data.recently_fired.slice(0, 4).map((event) => (
              <li key={`${event.alert_id}-${event.triggered_at}`} className={styles.firedItem}>
                <div>
                  <p className={styles.message}>{event.message}</p>
                  {event.symbol ? <span className={`num ${styles.symbol}`}>{event.symbol}</span> : null}
                </div>
                <time className={styles.time} dateTime={event.triggered_at}>
                  {new Date(event.triggered_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
                </time>
              </li>
            ))}
          </ul>
        )
      ) : null}

      <div className={styles.configuredSection}>
        <span className={styles.sectionLabel}>Configured</span>
        {configured.isLoading ? (
          <SkeletonCard />
        ) : configured.isError ? (
          <ErrorState message={apiErrorMessage(configured.error)} onRetry={() => void configured.refetch()} />
        ) : configured.data && configured.data.length > 0 ? (
          <ul className={styles.configuredList}>
            {configured.data.slice(0, 4).map((alert) => (
              <li key={alert.id} className={styles.configuredRow}>
                <span className={`num ${styles.symbol}`}>{alert.symbol ?? '—'}</span>
                <span className={styles.type}>{alert.alert_type}</span>
                {Object.keys(alert.parameters).length > 0 ? (
                  <span className={styles.params}>
                    {Object.entries(alert.parameters)
                      .map(([key, value]) => `${key}: ${value}`)
                      .join(', ')}
                  </span>
                ) : (
                  <span className={styles.params} />
                )}
                <Badge tone={alert.enabled ? 'positive' : 'neutral'}>{alert.enabled ? 'Enabled' : 'Disabled'}</Badge>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No alerts configured" description="Alerts you create will appear here." />
        )}
      </div>
    </Card>
  )
}
