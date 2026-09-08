import { useQueryClient } from '@tanstack/react-query'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { SkeletonCard } from '../components/ui/Skeleton'
import { Table, TableCell, TableHeadCell } from '../components/ui/Table'
import { apiErrorMessage } from '../api/client'
import { useLearningDashboard } from '../features/dashboard/hooks'
import { LearningHeader } from '../features/learning/LearningHeader'
import { LearningStatusPanel } from '../features/learning/LearningStatusPanel'
import { EngineAccuracyPanel } from '../features/learning/EngineAccuracyPanel'
import { CalibrationPanel } from '../features/learning/CalibrationPanel'
import { ShadowEvaluationPanel } from '../features/learning/ShadowEvaluationPanel'
import { DriftAlertsPanel } from '../features/learning/DriftAlertsPanel'
import { PromotionRecommendationsPanel } from '../features/learning/PromotionRecommendationsPanel'
import styles from './LearningPage.module.css'

/**
 * /learning - Continuous Learning intelligence. Every section is
 * backed by GET /dashboard/engines and/or GET /dashboard/learning
 * (dashboard/models.py), reusing the exact same `useEngineDashboard`/
 * `useLearningDashboard`/`useOverview` hooks the Dashboard already
 * uses - no duplicate fetch. Nothing here computes accuracy, weights,
 * calibration, or drift itself; every value is the backend's own
 * (WEB STEP 7).
 */
export function LearningPage() {
  const queryClient = useQueryClient()
  const rankings = useLearningDashboard()

  function handleRefresh() {
    void queryClient.invalidateQueries({ queryKey: ['dashboard', 'engines'] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard', 'learning'] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard', 'overview'] })
  }

  return (
    <div className={styles.page}>
      <LearningHeader onRefresh={handleRefresh} isRefreshing={rankings.isFetching} />

      <LearningStatusPanel />

      <Card padding="none">
        <div style={{ padding: 'var(--space-5)', paddingBottom: 0 }}>
          <CardHeader>
            <div>
              <CardTitle>Engine ranking</CardTitle>
              <CardSubtitle>By 30-day accuracy</CardSubtitle>
            </div>
          </CardHeader>
        </div>

        {rankings.isLoading ? (
          <div style={{ padding: 'var(--space-5)' }}>
            <SkeletonCard />
          </div>
        ) : rankings.isError ? (
          <div style={{ padding: 'var(--space-5)' }}>
            <ErrorState message={apiErrorMessage(rankings.error)} onRetry={() => void rankings.refetch()} />
          </div>
        ) : !rankings.data || rankings.data.engine_rankings.length === 0 ? (
          <div style={{ padding: 'var(--space-5)' }}>
            <EmptyState title="No engine rankings yet" description="Appears once engines have accumulated evaluated samples." />
          </div>
        ) : (
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
              {rankings.data.engine_rankings.map((ranking) => (
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
        )}
      </Card>

      <div className={styles.grid}>
        <div className={styles.mainColumn}>
          <EngineAccuracyPanel />
          <CalibrationPanel />
          <ShadowEvaluationPanel />
        </div>
        <div className={styles.sideColumn}>
          <DriftAlertsPanel />
          <PromotionRecommendationsPanel />
        </div>
      </div>
    </div>
  )
}
