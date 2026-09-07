import { KpiCard } from '../../../components/ui/KpiCard'
import { useOverview } from '../hooks'
import { apiErrorMessage } from '../../../api/client'
import { ErrorState } from '../../../components/ui/ErrorState'
import styles from '../../../pages/DashboardPage.module.css'

/** Backed by GET /dashboard/overview (dashboard/models.py::OverviewMetrics) - every field here is real. */
export function KpiCardsSection() {
  const { data, isLoading, isError, error, refetch } = useOverview()

  if (isError) {
    return <ErrorState message={apiErrorMessage(error)} onRetry={() => void refetch()} />
  }

  return (
    <div className={styles.kpiRow}>
      <KpiCard label="Total portfolios" value={data?.total_portfolios} isLoading={isLoading} />
      <KpiCard label="Watchlists" value={data?.total_watchlists} isLoading={isLoading} />
      <KpiCard label="Active alerts" value={data?.total_alerts} isLoading={isLoading} />
      <KpiCard label="Active engines" value={data?.active_engines} isLoading={isLoading} />
    </div>
  )
}
