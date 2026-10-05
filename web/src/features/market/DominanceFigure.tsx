import { Card, CardHeader, CardTitle } from '../../components/ui/Card'
import { SkeletonCard } from '../../components/ui/Skeleton'
import styles from './DominanceFigure.module.css'

interface DominanceFigureProps {
  value: number | null
  isLoading: boolean
}

/**
 * The current BTC dominance percentage (BTC's share of total crypto
 * market cap), from GET /market/snapshot's btc_dominance_pct field -
 * a real CoinGecko figure, never fabricated. `value === null` means
 * the CoinGecko call failed this time; shown honestly as
 * "unavailable", never a stale or made-up number.
 */
export function DominanceFigure({ value, isLoading }: DominanceFigureProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>BTC Dominance</CardTitle>
      </CardHeader>
      {isLoading ? (
        <SkeletonCard />
      ) : (
        <p className={styles.value}>{value != null ? `${value.toFixed(1)}%` : 'unavailable'}</p>
      )}
    </Card>
  )
}
