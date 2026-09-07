import { Link } from 'react-router-dom'
import { Bar, BarChart, Tooltip as RechartsTooltip, XAxis, YAxis } from 'recharts'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../../components/ui/Card'
import { ChartContainer } from '../../../components/ui/ChartContainer'
import { useChartColors } from '../../../components/ui/useChartColors'
import { useLearningDashboard } from '../hooks'
import { apiErrorMessage } from '../../../api/client'
import styles from './LearningOverview.module.css'

/**
 * Backed by GET /dashboard/learning (dashboard/models.py::LearningDashboardView.engine_rankings)
 * only - other fields on that view (recent_samples, promotion_candidates,
 * calibration_history) are typed as opaque arrays because the backend
 * hasn't stabilized their shape, so nothing is rendered from them here
 * rather than guessing a structure (WEB STEP 2 §10). Deliberately
 * smaller/quieter than the portfolio and market sections above it.
 */
export function LearningOverview() {
  const { data, isLoading, isError, error, refetch } = useLearningDashboard()
  const colors = useChartColors()

  const rankings = [...(data?.engine_rankings ?? [])].sort((a, b) => a.rank - b.rank)

  return (
    <Card padding="compact" className={styles.card}>
      <CardHeader>
        <div>
          <CardTitle className={styles.title}>Learning</CardTitle>
          <CardSubtitle>Continuous Learning engine ranking</CardSubtitle>
        </div>
        <Link to="/learning" className={styles.viewAll}>
          View all →
        </Link>
      </CardHeader>

      <ChartContainer
        label="Engine accuracy ranking"
        height={160}
        isLoading={isLoading}
        error={isError ? apiErrorMessage(error) : null}
        onRetry={() => void refetch()}
        isEmpty={rankings.length === 0}
        emptyVariant="unavailable"
        emptyTitle="No rankings yet"
        emptyDescription="Rankings appear once engines have accumulated evaluated samples."
      >
        <BarChart data={rankings} layout="vertical" margin={{ left: 8, right: 24 }}>
          <XAxis type="number" domain={[0, 1]} stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} />
          <YAxis type="category" dataKey="engine_name" stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} width={80} />
          <RechartsTooltip
            formatter={(value) => `${(Number(value) * 100).toFixed(1)}%`}
            contentStyle={{ background: colors.border, border: 'none', borderRadius: 6, fontSize: 12 }}
          />
          <Bar dataKey="accuracy" fill={colors.info} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ChartContainer>
    </Card>
  )
}
