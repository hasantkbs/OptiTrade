import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { SkeletonCard } from '../components/ui/Skeleton'
import { Table, TableCell, TableHeadCell } from '../components/ui/Table'
import { usePortfolioList } from '../features/dashboard/hooks'
import { apiErrorMessage } from '../api/client'

/** Backed by GET /portfolios (portfolio/models.py::Portfolio). */
export function PortfolioPage() {
  const { data, isLoading, isError, error, refetch } = usePortfolioList()

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
        <EmptyState
          title="No portfolios yet"
          description="Portfolios you create through the API will appear here."
        />
      </Card>
    )
  }

  return (
    <Card padding="none">
      <Table>
        <thead>
          <tr>
            <TableHeadCell>Name</TableHeadCell>
            <TableHeadCell>Base currency</TableHeadCell>
            <TableHeadCell align="right">Created</TableHeadCell>
          </tr>
        </thead>
        <tbody>
          {data.map((portfolio) => (
            <tr key={portfolio.id}>
              <TableCell>{portfolio.name}</TableCell>
              <TableCell numeric>{portfolio.base_currency}</TableCell>
              <TableCell align="right">{new Date(portfolio.created_at).toLocaleDateString()}</TableCell>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  )
}
