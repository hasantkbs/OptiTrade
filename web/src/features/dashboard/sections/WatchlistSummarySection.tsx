import { Card, CardHeader, CardSubtitle, CardTitle } from '../../../components/ui/Card'
import { Badge } from '../../../components/ui/Badge'
import { EmptyState } from '../../../components/ui/EmptyState'
import { ErrorState } from '../../../components/ui/ErrorState'
import { SkeletonCard } from '../../../components/ui/Skeleton'
import { useWatchlistDashboard } from '../hooks'
import { apiErrorMessage } from '../../../api/client'
import styles from './WatchlistSummarySection.module.css'

/** Backed by GET /dashboard/watchlists (dashboard/models.py::WatchlistDashboardView) - summary counts and
 * the most-tracked symbols, the only "opportunity" signal this endpoint actually exposes today. */
export function WatchlistSummarySection() {
  const { data, isLoading, isError, error, refetch } = useWatchlistDashboard()

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Watchlist summary</CardTitle>
          <CardSubtitle>Across all of your watchlists</CardSubtitle>
        </div>
      </CardHeader>

      {isLoading ? <SkeletonCard /> : null}
      {isError ? <ErrorState message={apiErrorMessage(error)} onRetry={() => void refetch()} /> : null}

      {data ? (
        data.total_watchlists === 0 ? (
          <EmptyState title="No watchlists yet" description="Symbols you track will show up here." />
        ) : (
          <div className={styles.body}>
            <div className={styles.stats}>
              <span>
                <strong className="num">{data.total_items}</strong> items
              </span>
              <span>
                <strong className="num">{data.total_favorites}</strong> favorites
              </span>
            </div>
            {data.most_tracked_symbols.length > 0 ? (
              <div className={styles.symbols}>
                {data.most_tracked_symbols.slice(0, 8).map((symbol) => (
                  <Badge key={symbol} tone="neutral">
                    <span className="num">{symbol}</span>
                  </Badge>
                ))}
              </div>
            ) : null}
          </div>
        )
      ) : null}
    </Card>
  )
}
