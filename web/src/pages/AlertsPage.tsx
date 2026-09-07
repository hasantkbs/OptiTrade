import { Card } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { SkeletonCard } from '../components/ui/Skeleton'
import { Table, TableCell, TableHeadCell } from '../components/ui/Table'
import { useAlerts } from '../features/dashboard/hooks'
import { apiErrorMessage } from '../api/client'

/** Backed by GET /alerts (watchlist/models.py::Alert). */
export function AlertsPage() {
  const { data, isLoading, isError, error, refetch } = useAlerts()

  if (isLoading) {
    return (
      <Card>
        <SkeletonCard />
      </Card>
    )
  }

  if (isError) {
    return (
      <Card>
        <ErrorState message={apiErrorMessage(error)} onRetry={() => void refetch()} />
      </Card>
    )
  }

  if (!data || data.length === 0) {
    return (
      <Card>
        <EmptyState title="No alerts configured" description="Alerts you create will appear here." />
      </Card>
    )
  }

  return (
    <Card padding="none">
      <Table>
        <thead>
          <tr>
            <TableHeadCell>Symbol</TableHeadCell>
            <TableHeadCell>Category</TableHeadCell>
            <TableHeadCell>Type</TableHeadCell>
            <TableHeadCell align="right">Status</TableHeadCell>
          </tr>
        </thead>
        <tbody>
          {data.map((alert) => (
            <tr key={alert.id}>
              <TableCell numeric>{alert.symbol ?? '—'}</TableCell>
              <TableCell>{alert.category}</TableCell>
              <TableCell>{alert.alert_type}</TableCell>
              <TableCell align="right">
                <Badge tone={alert.enabled ? 'positive' : 'neutral'}>{alert.enabled ? 'Enabled' : 'Disabled'}</Badge>
              </TableCell>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  )
}
