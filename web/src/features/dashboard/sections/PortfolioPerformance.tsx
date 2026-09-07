import { useState } from 'react'
import { Bar, BarChart, Tooltip as RechartsTooltip, XAxis, YAxis } from 'recharts'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../../components/ui/Card'
import { ChartContainer } from '../../../components/ui/ChartContainer'
import { Dropdown } from '../../../components/ui/Dropdown'
import { Tabs } from '../../../components/ui/Tabs'
import { useChartColors } from '../../../components/ui/useChartColors'
import { EmptyState } from '../../../components/ui/EmptyState'
import { ErrorState } from '../../../components/ui/ErrorState'
import { SkeletonCard } from '../../../components/ui/Skeleton'
import { apiErrorMessage } from '../../../api/client'
import { usePortfolioDashboard, usePortfolioList } from '../hooks'
import styles from './PortfolioPerformance.module.css'

function formatCurrency(value: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 0 }).format(value)
}

type AllocationView = 'symbol' | 'sector'

/**
 * Backed by GET /portfolios + GET /dashboard/portfolios/{id}
 * (portfolio/models.py::PortfolioDashboard). The backend exposes only a
 * current snapshot for a regular portfolio - no historical equity
 * series - so this deliberately visualizes the real cross-sectional
 * allocation breakdown (a genuine chart-worthy dataset) instead of
 * inventing an equity curve from a single point (WEB STEP 2 §5).
 */
export function PortfolioPerformance() {
  const portfolios = usePortfolioList()
  const [selectedId, setSelectedId] = useState<number | undefined>(undefined)
  const [allocationView, setAllocationView] = useState<AllocationView>('symbol')
  const colors = useChartColors()

  const list = portfolios.data ?? []
  const active = list.find((p) => p.id === selectedId) ?? list[0]
  const dashboard = usePortfolioDashboard(active?.id ?? undefined)

  if (portfolios.isLoading) {
    return (
      <Card>
        <SkeletonCard />
      </Card>
    )
  }

  if (portfolios.isError) {
    return (
      <Card>
        <ErrorState message={apiErrorMessage(portfolios.error)} onRetry={() => void portfolios.refetch()} />
      </Card>
    )
  }

  if (list.length === 0 || !active) {
    return (
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Portfolio</CardTitle>
            <CardSubtitle>Allocation &amp; risk</CardSubtitle>
          </div>
        </CardHeader>
        <EmptyState title="No portfolio yet" description="Create a portfolio to see its allocation and risk profile here." />
      </Card>
    )
  }

  const data = dashboard.data?.dashboard
  const allocation = data?.allocation
  const risk = data?.risk
  const allocationSource = allocationView === 'symbol' ? allocation?.by_symbol_pct : allocation?.by_sector_pct
  const chartData = Object.entries(allocationSource ?? {})
    .map(([key, pct]) => ({ key, pct }))
    .sort((a, b) => b.pct - a.pct)
    .slice(0, 8)

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Portfolio</CardTitle>
          <CardSubtitle>{active.name}</CardSubtitle>
        </div>
        {list.length > 1 ? (
          <Dropdown
            trigger={<span className={styles.selectorTrigger}>{active.name} ▾</span>}
            items={list.map((portfolio) => ({
              label: portfolio.name,
              onSelect: () => setSelectedId(portfolio.id ?? undefined),
            }))}
          />
        ) : null}
      </CardHeader>

      {dashboard.isLoading ? (
        <SkeletonCard />
      ) : dashboard.isError ? (
        <ErrorState message={apiErrorMessage(dashboard.error)} onRetry={() => void dashboard.refetch()} />
      ) : data ? (
        <div className={styles.body}>
          <div className={styles.scalarGrid}>
            <div className={styles.stat}>
              <span className={styles.label}>Cash balance</span>
              <span className={`num ${styles.value}`}>{formatCurrency(data.cash_balance, active.base_currency)}</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.label}>Realized P&amp;L</span>
              <span className={`num ${styles.value} ${data.realized_pnl >= 0 ? styles.positive : styles.negative}`}>
                {formatCurrency(data.realized_pnl, active.base_currency)}
              </span>
            </div>
            <div className={styles.stat}>
              <span className={styles.label}>Cash weight</span>
              <span className={`num ${styles.value}`}>{allocation ? `${allocation.cash_weight_pct.toFixed(1)}%` : '—'}</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.label}>Volatility</span>
              <span className={`num ${styles.value}`}>{risk ? `${risk.volatility_pct.toFixed(1)}%` : '—'}</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.label}>Beta</span>
              <span className={`num ${styles.value}`}>{risk?.beta != null ? risk.beta.toFixed(2) : '—'}</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.label}>Diversification</span>
              <span className={`num ${styles.value}`}>{risk ? risk.diversification_score.toFixed(2) : '—'}</span>
            </div>
          </div>

          <div className={styles.allocationSection}>
            <span className={styles.sectionLabel}>Allocation breakdown</span>
            <Tabs
              items={[
                { id: 'symbol', label: 'By symbol', content: null },
                { id: 'sector', label: 'By sector', content: null },
              ]}
              active={allocationView}
              onChange={(id) => setAllocationView(id as AllocationView)}
            />
            <ChartContainer
              label={`Portfolio allocation by ${allocationView}`}
              height={220}
              isEmpty={chartData.length === 0}
              emptyTitle="No positions yet"
              emptyDescription="Allocation breakdown will appear once this portfolio holds positions."
            >
              <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 24 }}>
                <XAxis type="number" unit="%" stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} />
                <YAxis
                  type="category"
                  dataKey="key"
                  stroke={colors.textSecondary}
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                  width={72}
                />
                <RechartsTooltip
                  formatter={(value) => `${Number(value).toFixed(1)}%`}
                  contentStyle={{ background: colors.border, border: 'none', borderRadius: 6, fontSize: 12 }}
                />
                <Bar dataKey="pct" fill={colors.accent} radius={[0, 4, 4, 0]} />
              </BarChart>
            </ChartContainer>
          </div>
        </div>
      ) : null}
    </Card>
  )
}
