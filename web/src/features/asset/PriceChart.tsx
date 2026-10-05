import { Area, AreaChart, Bar, BarChart, Line, LineChart, Tooltip as RechartsTooltip, XAxis, YAxis } from 'recharts'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { ChartContainer } from '../../components/ui/ChartContainer'
import { Tabs } from '../../components/ui/Tabs'
import { useChartColors } from '../../components/ui/useChartColors'
import type { ChartPeriod, ChartResponse } from '../../api/types'
import styles from './PriceChart.module.css'

const PERIODS: { id: ChartPeriod; label: string }[] = [
  { id: '1mo', label: '1M' },
  { id: '3mo', label: '3M' },
  { id: '6mo', label: '6M' },
  { id: '1y', label: '1Y' },
]

interface PriceChartProps {
  chart?: ChartResponse
  isLoading: boolean
  isError: boolean
  errorMessage?: string
  onRetry: () => void
  period: ChartPeriod
  onPeriodChange: (period: ChartPeriod) => void
}

/**
 * Backed entirely by GET /chart/{symbol} (models/schemas.py::
 * ChartResponse) - a genuine historical series (`points[]`), not a
 * single scalar stretched into a fake line (WEB STEP 4 §4). RSI is
 * shown only when the backend actually computed it for enough points
 * (main.py requires >=15 data points before it starts populating
 * `ChartPoint.rsi`) - never backfilled or estimated on the frontend.
 */
export function PriceChart({ chart, isLoading, isError, errorMessage, onRetry, period, onPeriodChange }: PriceChartProps) {
  const colors = useChartColors()
  const points = chart?.points ?? []
  const hasRsi = points.some((p) => p.rsi != null)

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Price history</CardTitle>
          <CardSubtitle>
            {chart ? `${chart.change_pct >= 0 ? '+' : ''}${chart.change_pct.toFixed(2)}% over this period · High ${chart.high.toLocaleString()} · Low ${chart.low.toLocaleString()}` : 'Historical close price'}
          </CardSubtitle>
        </div>
      </CardHeader>

      <Tabs
        items={PERIODS.map((p) => ({ id: p.id, label: p.label, content: null }))}
        active={period}
        onChange={(id) => onPeriodChange(id as ChartPeriod)}
      />

      <ChartContainer
        label={`${chart?.symbol ?? ''} closing price, ${period}`}
        height={280}
        isLoading={isLoading}
        error={isError ? errorMessage ?? "Couldn't load chart" : null}
        onRetry={onRetry}
        isEmpty={!isLoading && !isError && points.length === 0}
        emptyTitle="No chart data available"
        emptyDescription="The backend has no historical price data for this symbol and period."
      >
        <AreaChart data={points}>
          <defs>
            <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={colors.accent} stopOpacity={0.25} />
              <stop offset="100%" stopColor={colors.accent} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="date" stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} minTickGap={40} />
          <YAxis stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} width={56} domain={['auto', 'auto']} />
          <RechartsTooltip
            contentStyle={{ background: colors.border, border: 'none', borderRadius: 6, fontSize: 12 }}
            formatter={(value, name) => [Number(value).toLocaleString(), name === 'close' ? 'Close' : name]}
            labelFormatter={(label) => label}
          />
          <Area type="monotone" dataKey="close" stroke={colors.accent} strokeWidth={2} fill="url(#priceFill)" />
        </AreaChart>
      </ChartContainer>

      {hasRsi ? (
        <div className={styles.rsiSection}>
          <span className={styles.rsiLabel}>RSI</span>
          <ChartContainer label={`${chart?.symbol ?? ''} RSI, ${period}`} height={90} isEmpty={false}>
            <LineChart data={points}>
              <XAxis dataKey="date" hide />
              <YAxis domain={[0, 100]} hide />
              <RechartsTooltip
                contentStyle={{ background: colors.border, border: 'none', borderRadius: 6, fontSize: 12 }}
                formatter={(value) => [value != null ? Number(value).toFixed(1) : '—', 'RSI']}
              />
              <Line type="monotone" dataKey="rsi" stroke={colors.info} strokeWidth={1.5} dot={false} connectNulls />
            </LineChart>
          </ChartContainer>
        </div>
      ) : null}

      <div className={styles.volumeSection}>
        <span className={styles.rsiLabel}>Volume</span>
        <ChartContainer label={`${chart?.symbol ?? ''} volume, ${period}`} height={90} isEmpty={false}>
          <BarChart data={points}>
            <XAxis dataKey="date" hide />
            <YAxis hide />
            <RechartsTooltip
              contentStyle={{ background: colors.border, border: 'none', borderRadius: 6, fontSize: 12 }}
              formatter={(value) => [Number(value).toLocaleString(), 'Volume']}
            />
            <Bar dataKey="volume" fill={colors.textSecondary} radius={[2, 2, 0, 0]} />
          </BarChart>
        </ChartContainer>
      </div>
    </Card>
  )
}
