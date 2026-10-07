import { useNavigate } from 'react-router-dom'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { SkeletonCard } from '../components/ui/Skeleton'
import { Table, TableCell, TableHeadCell } from '../components/ui/Table'
import { Tooltip } from '../components/ui/Tooltip'
import { useMarketDashboard } from '../features/dashboard/hooks'
import { SymbolSearch } from '../features/market/SymbolSearch'
import { apiErrorMessage } from '../api/client'

/** Backed by GET /dashboard/market (dashboard/models.py::MarketDashboardView) - sector heatmap is real. */
export function AssetsPage() {
  const { data, isLoading, isError, error, refetch } = useMarketDashboard()
  const navigate = useNavigate()

  return (
    <Card padding="none">
      <div style={{ padding: 'var(--space-5)', paddingBottom: 0 }}>
        <CardHeader>
          <div>
            <CardTitle>Sector overview</CardTitle>
            <CardSubtitle>Opportunity score and trend by sector</CardSubtitle>
          </div>
        </CardHeader>

        <div style={{ maxWidth: '24rem', marginBottom: 'var(--space-5)' }}>
          <SymbolSearch
            label="Look up a stock or crypto"
            onSelect={(symbol) => navigate(`/assets/${symbol}`)}
          />
        </div>
      </div>

      {isLoading ? (
        <div style={{ padding: 'var(--space-5)' }}>
          <SkeletonCard />
        </div>
      ) : isError ? (
        <div style={{ padding: 'var(--space-5)' }}>
          <ErrorState message={apiErrorMessage(error)} onRetry={() => void refetch()} />
        </div>
      ) : !data || data.sector_heatmap.length === 0 ? (
        <div style={{ padding: 'var(--space-5)' }}>
          <EmptyState title="No sector data yet" description="Sector opportunity scores will appear here once available." />
        </div>
      ) : (
        <Table>
          <thead>
            <tr>
              <TableHeadCell>Sector</TableHeadCell>
              <TableHeadCell align="right">
                <Tooltip content="0-100. Combines each sector's technical trend, news sentiment and price momentum into one score - higher means a stronger buy signal across that sector's stocks.">
                  Opportunity score (0-100)
                </Tooltip>
              </TableHeadCell>
              <TableHeadCell align="right">
                <Tooltip content="Average daily price change, as a percentage, across the sector's tracked stocks.">
                  Avg daily change
                </Tooltip>
              </TableHeadCell>
              <TableHeadCell align="right">Trend</TableHeadCell>
            </tr>
          </thead>
          <tbody>
            {data.sector_heatmap.map((sector) => (
              <tr key={sector.sector}>
                <TableCell>{sector.sector}</TableCell>
                <TableCell align="right" numeric>
                  {sector.opportunity_score.toFixed(1)}
                </TableCell>
                <TableCell align="right" numeric>
                  {sector.avg_change_pct.toFixed(2)}%
                </TableCell>
                <TableCell align="right">{sector.trend}</TableCell>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  )
}
