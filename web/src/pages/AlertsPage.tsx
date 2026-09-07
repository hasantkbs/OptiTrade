import { useQueryClient } from '@tanstack/react-query'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { ErrorState } from '../components/ui/ErrorState'
import { SkeletonCard } from '../components/ui/Skeleton'
import { apiErrorMessage } from '../api/client'
import { useAlerts } from '../features/dashboard/hooks'
import { AlertsSummary } from '../features/alerts/AlertsSummary'
import { AlertList } from '../features/alerts/AlertList'
import { CreateAlertForm } from '../features/alerts/CreateAlertForm'
import { ScanPanel } from '../features/alerts/ScanPanel'
import styles from './AlertsPage.module.css'

/**
 * Backed by GET /alerts (watchlist/models.py::Alert), reusing the exact
 * same `useAlerts` hook the Dashboard's AlertsOverview card already
 * uses - one shared cache entry, not a second fetch of the same
 * resource (WEB STEP 6).
 */
export function AlertsPage() {
  const queryClient = useQueryClient()
  const { data, isLoading, isError, error, refetch, isFetching } = useAlerts()

  function handleRefresh() {
    void queryClient.invalidateQueries({ queryKey: ['alerts'] })
  }

  if (isLoading) {
    return (
      <div className={styles.page}>
        <Card>
          <SkeletonCard />
        </Card>
      </div>
    )
  }

  if (isError) {
    return (
      <div className={styles.page}>
        <Card>
          <ErrorState message={apiErrorMessage(error)} onRetry={() => void refetch()} />
        </Card>
      </div>
    )
  }

  const alerts = data ?? []

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Alerts</h1>
          <p className={styles.subtitle}>Price, technical, decision, news and portfolio conditions evaluated by the backend's Alert Engine.</p>
        </div>
        <Button variant="secondary" size="sm" onClick={handleRefresh} isLoading={isFetching}>
          Refresh
        </Button>
      </div>

      <AlertsSummary alerts={alerts} />

      <div className={styles.grid}>
        <div className={styles.mainColumn}>
          <AlertList alerts={alerts} />
        </div>
        <div className={styles.sideColumn}>
          <CreateAlertForm />
          <ScanPanel />
        </div>
      </div>
    </div>
  )
}
