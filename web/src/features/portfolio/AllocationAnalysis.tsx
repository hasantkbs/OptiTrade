import { useState } from 'react'
import { Bar, BarChart, Tooltip as RechartsTooltip, XAxis, YAxis } from 'recharts'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { ChartContainer } from '../../components/ui/ChartContainer'
import { Tabs } from '../../components/ui/Tabs'
import { useChartColors } from '../../components/ui/useChartColors'
import type { AllocationBreakdown } from '../../api/types'
import styles from './AllocationAnalysis.module.css'

type View = 'symbol' | 'sector'

interface AllocationAnalysisProps {
  allocation: AllocationBreakdown
}

/**
 * Backed entirely by GET /dashboard/portfolios/{id}'s `allocation`
 * field (portfolio/models.py::AllocationBreakdown.by_symbol_pct /
 * by_sector_pct). The "largest allocation" line is a plain factual
 * read of the max entry already in that real breakdown - not an
 * invented concentration classification (WEB STEP 3 §5).
 */
export function AllocationAnalysis({ allocation }: AllocationAnalysisProps) {
  const [view, setView] = useState<View>('symbol')
  const colors = useChartColors()

  const source = view === 'symbol' ? allocation.by_symbol_pct : allocation.by_sector_pct
  const chartData = Object.entries(source)
    .map(([key, pct]) => ({ key, pct }))
    .sort((a, b) => b.pct - a.pct)
  const largest = chartData[0]

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Allocation</CardTitle>
          <CardSubtitle>How this portfolio's value is distributed</CardSubtitle>
        </div>
      </CardHeader>

      <Tabs
        items={[
          { id: 'symbol', label: 'By symbol', content: null },
          { id: 'sector', label: 'By sector', content: null },
        ]}
        active={view}
        onChange={(id) => setView(id as View)}
      />

      <ChartContainer
        label={`Portfolio allocation by ${view}`}
        height={Math.max(180, chartData.length * 32)}
        isEmpty={chartData.length === 0}
        emptyTitle="No positions yet"
        emptyDescription="Allocation breakdown will appear once this portfolio holds positions."
      >
        <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 32 }}>
          <XAxis type="number" unit="%" stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} />
          <YAxis type="category" dataKey="key" stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} width={80} />
          <RechartsTooltip
            formatter={(value) => `${Number(value).toFixed(1)}%`}
            contentStyle={{ background: colors.border, border: 'none', borderRadius: 6, fontSize: 12 }}
          />
          <Bar dataKey="pct" fill={colors.accent} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ChartContainer>

      {largest ? (
        <p className={styles.callout}>
          Largest allocation: <span className="num">{largest.key}</span> at <span className="num">{largest.pct.toFixed(1)}%</span> of
          portfolio value.
        </p>
      ) : null}

      <p className={styles.note}>Cash weight: {allocation.cash_weight_pct.toFixed(1)}% (not part of the {view} breakdown above).</p>
    </Card>
  )
}
