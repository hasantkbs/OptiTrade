import { apiErrorMessage } from '../api/client'
import { useMarketSnapshot } from '../features/dashboard/hooks'
import { IndexChart } from '../features/market/IndexChart'
import { DominanceFigure } from '../features/market/DominanceFigure'
import { MarketSummary } from '../features/market/MarketSummary'
import styles from './MarketSnapshotPage.module.css'

export function MarketSnapshotPage() {
  const snapshot = useMarketSnapshot()

  return (
    <div className={styles.page}>
      <div className={styles.chartsRow}>
        <IndexChart
          title="BIST 100"
          chart={snapshot.data?.bist100 ?? null}
          isLoading={snapshot.isLoading}
          isError={snapshot.isError}
          errorMessage={snapshot.isError ? apiErrorMessage(snapshot.error) : undefined}
        />
        <IndexChart
          title="Bitcoin"
          chart={snapshot.data?.btc ?? null}
          isLoading={snapshot.isLoading}
          isError={snapshot.isError}
          errorMessage={snapshot.isError ? apiErrorMessage(snapshot.error) : undefined}
        />
        <DominanceFigure value={snapshot.data?.btc_dominance_pct ?? null} isLoading={snapshot.isLoading} />
      </div>

      <MarketSummary />
    </div>
  )
}
