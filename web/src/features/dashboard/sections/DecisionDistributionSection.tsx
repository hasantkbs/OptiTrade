import { Bar, BarChart, Tooltip as RechartsTooltip, XAxis, YAxis } from 'recharts'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../../components/ui/Card'
import { ChartContainer } from '../../../components/ui/ChartContainer'
import { useChartColors } from '../../../components/ui/useChartColors'
import { useEngineDashboard } from '../hooks'
import { apiErrorMessage } from '../../../api/client'

/** Backed by GET /dashboard/engines (dashboard/models.py::EngineDashboardView.regime_distribution) - the
 * real count of scans per detected market regime, not a fabricated decision breakdown. */
export function DecisionDistributionSection() {
  const { data, isLoading, isError, error, refetch } = useEngineDashboard()
  const colors = useChartColors()

  const entries = Object.entries(data?.regime_distribution ?? {})
  const chartData = entries.map(([regime, count]) => ({ regime, count }))

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Regime distribution</CardTitle>
          <CardSubtitle>Detected market regime across recent scans</CardSubtitle>
        </div>
      </CardHeader>
      <ChartContainer
        label="Market regime distribution"
        height={220}
        isLoading={isLoading}
        error={isError ? apiErrorMessage(error) : null}
        onRetry={() => void refetch()}
        isEmpty={chartData.length === 0}
        emptyTitle="No regime data yet"
        emptyDescription="This chart will populate once regime scans have run."
      >
        <BarChart data={chartData}>
          <XAxis dataKey="regime" stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} />
          <YAxis stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} width={28} allowDecimals={false} />
          <RechartsTooltip contentStyle={{ background: colors.border, border: 'none', borderRadius: 6, fontSize: 12 }} />
          <Bar dataKey="count" fill={colors.info} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ChartContainer>
    </Card>
  )
}
