import { useNavigate } from 'react-router-dom'
import { apiErrorMessage } from '../api/client'
import { useMarketSnapshot } from '../features/dashboard/hooks'
import { IndexChart } from '../features/market/IndexChart'
import { DominanceFigure } from '../features/market/DominanceFigure'
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

      <MarketSummary />
    </div>
  )
}
