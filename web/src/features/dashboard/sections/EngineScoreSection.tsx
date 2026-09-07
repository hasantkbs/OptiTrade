import { Line, LineChart, Tooltip as RechartsTooltip, XAxis, YAxis } from 'recharts'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../../components/ui/Card'
import { ChartContainer } from '../../../components/ui/ChartContainer'
import { useChartColors } from '../../../components/ui/useChartColors'
import { useEngineDashboard } from '../hooks'
import { apiErrorMessage } from '../../../api/client'

function formatTime(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

/** Backed by GET /dashboard/engines (dashboard/models.py::EngineDashboardView.confidence_history) - a real
 * time series of Decision Engine confidence, not synthesized. */
export function EngineScoreSection() {
  const { data, isLoading, isError, error, refetch } = useEngineDashboard()
  const colors = useChartColors()

  const points = data?.confidence_history ?? []

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Engine confidence</CardTitle>
          <CardSubtitle>Decision Engine aggregate confidence over time</CardSubtitle>
        </div>
      </CardHeader>
      <ChartContainer
        label="Engine confidence over time"
        isLoading={isLoading}
        error={isError ? apiErrorMessage(error) : null}
        onRetry={() => void refetch()}
        isEmpty={points.length === 0}
        emptyTitle="No confidence history yet"
        emptyDescription="This chart will populate once the Decision Engine has recorded confidence scores."
      >
        <LineChart data={points.map((p) => ({ ...p, label: formatTime(p.timestamp) }))}>
          <XAxis dataKey="label" stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} />
          <YAxis stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} width={36} />
          <RechartsTooltip
            contentStyle={{ background: colors.border, border: 'none', borderRadius: 6, fontSize: 12 }}
          />
          <Line type="monotone" dataKey="value" stroke={colors.accent} strokeWidth={2} dot={false} />
        </LineChart>
      </ChartContainer>
    </Card>
  )
}
