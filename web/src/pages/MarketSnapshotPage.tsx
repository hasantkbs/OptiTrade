import { useNavigate } from 'react-router-dom'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../components/ui/Card'
import { apiErrorMessage } from '../api/client'
import { useMarketSnapshot } from '../features/dashboard/hooks'
import { IndexChart } from '../features/market/IndexChart'
import { DominanceFigure } from '../features/market/DominanceFigure'
import { MarketOpportunities } from '../features/market/MarketOpportunities'
import { MarketSummary } from '../features/market/MarketSummary'
import { SymbolSearch } from '../features/market/SymbolSearch'
import styles from './MarketSnapshotPage.module.css'

export function MarketSnapshotPage() {
  const snapshot = useMarketSnapshot()
  const navigate = useNavigate()

  return (
    <div className={styles.page}>
      <div style={{ maxWidth: '24rem', marginBottom: 'var(--space-5)' }}>
        <SymbolSearch
          label="Look up a stock or crypto"
          onSelect={(symbol) => navigate(`/assets/${symbol}`)}
        />
      </div>

      <div className={styles.chartsRow}>
        <IndexChart
          title="BIST 100"
          chart={snapshot.data?.bist100 ?? null}
          isLoading={snapshot.isLoading}
          isError={snapshot.isError}
          errorMessage={snapshot.isError ? apiErrorMessage(snapshot.error) : undefined}
          onRetry={() => void snapshot.refetch()}
        />
        <IndexChart
          title="Bitcoin"
          chart={snapshot.data?.btc ?? null}
          isLoading={snapshot.isLoading}
          isError={snapshot.isError}
          errorMessage={snapshot.isError ? apiErrorMessage(snapshot.error) : undefined}
          onRetry={() => void snapshot.refetch()}
        />
        <DominanceFigure value={snapshot.data?.btc_dominance_pct ?? null} isLoading={snapshot.isLoading} />
      </div>

      <Card style={{ marginTop: 'var(--space-5)' }}>
        <CardHeader>
          <div>
            <CardTitle>Top opportunities</CardTitle>
            <CardSubtitle>The model's highest-ranked picks per market, updated every 5 minutes</CardSubtitle>
          </div>
        </CardHeader>
        <MarketOpportunities />
      </Card>

      <MarketSummary />
    </div>
  )
}
