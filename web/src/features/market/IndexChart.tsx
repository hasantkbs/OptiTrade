import { Area, AreaChart, Tooltip as RechartsTooltip, XAxis, YAxis } from 'recharts'
import { Card, CardHeader, CardTitle } from '../../components/ui/Card'
import { ChartContainer } from '../../components/ui/ChartContainer'
import { useChartColors } from '../../components/ui/useChartColors'
import type { ChartResponse } from '../../api/types'
import styles from './IndexChart.module.css'

function slugify(value: string): string {
  return value.replace(/[^a-zA-Z0-9]/g, '-')
}

interface IndexChartProps {
  title: string
  chart: ChartResponse | null
  isLoading: boolean
  isError: boolean
  errorMessage?: string
  onRetry: () => void
}

/**
 * A plain price-line chart for a single market-context index
 * (BIST100 or BTC) on the simplified home page. Reuses PriceChart's
 * own charting approach (AreaChart via recharts) rather than a new
 * charting pattern - just without the period tabs or RSI sub-chart,
 * since this is a fixed-period context chart, not the full asset
 * price history view.
 */
export function IndexChart({ title, chart, isLoading, isError, errorMessage, onRetry }: IndexChartProps) {
  const colors = useChartColors()
  const points = chart?.points ?? []

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{title}</CardTitle>
          {chart ? (
            <span className={styles.changePct}>
              {chart.change_pct >= 0 ? '+' : ''}
              {chart.change_pct.toFixed(2)}%
            </span>
          ) : null}
        </div>
      </CardHeader>

      <ChartContainer
        label={`${title} price`}
        height={160}
        isLoading={isLoading}
        error={isError ? errorMessage ?? 'unavailable' : null}
        onRetry={onRetry}
        isEmpty={!isLoading && !isError && points.length === 0}
        emptyTitle="unavailable"
        emptyDescription="This chart isn't available right now."
      >
        <AreaChart data={points}>
          <defs>
            <linearGradient id={`indexFill-${slugify(title)}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={colors.accent} stopOpacity={0.25} />
              <stop offset="100%" stopColor={colors.accent} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="date" stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} minTickGap={40} />
          <YAxis stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} width={56} domain={['auto', 'auto']} />
          <RechartsTooltip
            contentStyle={{ background: colors.border, border: 'none', borderRadius: 6, fontSize: 12 }}
            formatter={(value) => [Number(value).toLocaleString(), 'Close']}
          />
          <Area type="monotone" dataKey="close" stroke={colors.accent} strokeWidth={2} fill={`url(#indexFill-${slugify(title)})`} />
        </AreaChart>
      </ChartContainer>
    </Card>
  )
}
