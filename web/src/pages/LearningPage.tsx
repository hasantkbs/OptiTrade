import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { SkeletonCard } from '../components/ui/Skeleton'
import { Table, TableCell, TableHeadCell } from '../components/ui/Table'
import { useLearningDashboard } from '../features/dashboard/hooks'
import { apiErrorMessage } from '../api/client'

/** Backed by GET /dashboard/learning (dashboard/models.py::LearningDashboardView.engine_rankings). */
export function LearningPage() {
  const { data, isLoading, isError, error, refetch } = useLearningDashboard()

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

  if (!data || data.engine_rankings.length === 0) {
    return (
      <Card>
        <EmptyState
          title="No engine rankings yet"
          description="Continuous Learning rankings will appear here once engines have accumulated evaluated samples."
        />
      </Card>
    )
  }

  return (
    <Card padding="none">
      <Table>
        <thead>
          <tr>
            <TableHeadCell align="right">Rank</TableHeadCell>
            <TableHeadCell>Engine</TableHeadCell>
            <TableHeadCell align="right">Accuracy</TableHeadCell>
            <TableHeadCell align="right">Current weight</TableHeadCell>
          </tr>
        </thead>
        <tbody>
          {data.engine_rankings.map((ranking) => (
            <tr key={`${ranking.engine_name}-${ranking.engine_version}`}>
              <TableCell align="right" numeric>
                {ranking.rank}
              </TableCell>
              <TableCell>
                {ranking.engine_name} <span style={{ color: 'var(--color-text-tertiary)' }}>v{ranking.engine_version}</span>
              </TableCell>
              <TableCell align="right" numeric>
                {(ranking.accuracy * 100).toFixed(1)}%
              </TableCell>
              <TableCell align="right" numeric>
                {ranking.current_weight !== null ? ranking.current_weight.toFixed(3) : '—'}
              </TableCell>
            </tr>
          ))}
        </tbody>
      </Table>
    </Card>
  )
}
