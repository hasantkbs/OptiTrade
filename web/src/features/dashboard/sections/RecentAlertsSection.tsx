import { Card, CardHeader, CardSubtitle, CardTitle } from '../../../components/ui/Card'
import { EmptyState } from '../../../components/ui/EmptyState'
import { ErrorState } from '../../../components/ui/ErrorState'
import { SkeletonCard } from '../../../components/ui/Skeleton'
import { useAlertDashboard } from '../hooks'
import { apiErrorMessage } from '../../../api/client'
import styles from './RecentAlertsSection.module.css'

/** Backed by GET /dashboard/alerts (dashboard/models.py::AlertDashboardView.recently_fired) - real trigger
 * events, not fabricated. */
export function RecentAlertsSection() {
  const { data, isLoading, isError, error, refetch } = useAlertDashboard()

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Recent alerts</CardTitle>
          <CardSubtitle>{data ? `${data.fired_last_24h} fired in the last 24h` : 'Last 24 hours'}</CardSubtitle>
        </div>
      </CardHeader>

      {isLoading ? <SkeletonCard /> : null}
      {isError ? <ErrorState message={apiErrorMessage(error)} onRetry={() => void refetch()} /> : null}

      {data ? (
        data.recently_fired.length === 0 ? (
          <EmptyState title="No alerts fired recently" description="Triggered alerts will appear here as they fire." />
        ) : (
          <ul className={styles.list}>
            {data.recently_fired.slice(0, 6).map((event) => (
              <li key={`${event.alert_id}-${event.triggered_at}`} className={styles.item}>
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
    </Card>
  )
}
