import { Link } from 'react-router-dom'
import { Bar, BarChart, Tooltip as RechartsTooltip, XAxis, YAxis } from 'recharts'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../../components/ui/Card'
import { Badge } from '../../../components/ui/Badge'
import { ChartContainer } from '../../../components/ui/ChartContainer'
import { useChartColors } from '../../../components/ui/useChartColors'
import { useMarketDashboard } from '../hooks'
import { apiErrorMessage } from '../../../api/client'
import styles from './MarketOverview.module.css'

function sentimentTone(label: string): 'positive' | 'negative' | 'neutral' {
  const lower = label.toLowerCase()
  if (lower.includes('pos') || lower.includes('bull')) return 'positive'
  if (lower.includes('neg') || lower.includes('bear')) return 'negative'
  return 'neutral'
}

/**
 * Backed by GET /dashboard/market (dashboard/models.py::MarketDashboardView).
 * A compact dashboard summary of the same real sector/news data the
 * full Assets page tables in detail - not a duplicated table, and no
 * fabricated "market status" indicator (WEB STEP 2 §9).
 */
export function MarketOverview() {
  const { data, isLoading, isError, error, refetch } = useMarketDashboard()
  const colors = useChartColors()

  const sectorData = [...(data?.sector_heatmap ?? [])]
    .sort((a, b) => b.opportunity_score - a.opportunity_score)
    .slice(0, 6)
  const news = data?.news_impact_summary.slice(0, 5) ?? []

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Market</CardTitle>
          <CardSubtitle>Sector opportunity &amp; news sentiment</CardSubtitle>
        </div>
        <Link to="/assets" className={styles.viewAll}>
          View all →
        </Link>
      </CardHeader>

      <ChartContainer
        label="Top sectors by opportunity score"
        height={180}
        isLoading={isLoading}
        error={isError ? apiErrorMessage(error) : null}
        onRetry={() => void refetch()}
        isEmpty={sectorData.length === 0}
        emptyTitle="No sector data yet"
        emptyDescription="Sector opportunity scores will appear here once available."
      >
        <BarChart data={sectorData} layout="vertical" margin={{ left: 8, right: 24 }}>
          <XAxis type="number" stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} />
          <YAxis type="category" dataKey="sector" stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} width={80} />
          <RechartsTooltip
            formatter={(value) => Number(value).toFixed(1)}
            contentStyle={{ background: colors.border, border: 'none', borderRadius: 6, fontSize: 12 }}
          />
          <Bar dataKey="opportunity_score" fill={colors.accent} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ChartContainer>

      {!isLoading && !isError && news.length > 0 ? (
        <div className={styles.newsSection}>
          <span className={styles.sectionLabel}>News sentiment</span>
          <ul className={styles.newsList}>
            {news.map((item) => (
              <li key={item.symbol} className={styles.newsRow}>
                <span className={`num ${styles.symbol}`}>{item.symbol}</span>
                <span className={styles.headlineCount}>{item.headline_count} headlines</span>
                <Badge tone={sentimentTone(item.sentiment_label)}>{item.sentiment_label}</Badge>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Card>
  )
}
