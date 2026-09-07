import { Link } from 'react-router-dom'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../../components/ui/Card'
import { Badge } from '../../../components/ui/Badge'
import { EmptyState } from '../../../components/ui/EmptyState'
import { ErrorState } from '../../../components/ui/ErrorState'
import { SkeletonCard } from '../../../components/ui/Skeleton'
import { useWatchlistDashboard, useWatchlistItems, useWatchlists } from '../hooks'
import { apiErrorMessage } from '../../../api/client'
import styles from './WatchlistIntelligence.module.css'

/**
 * Backed by GET /dashboard/watchlists (summary counts + most-tracked
 * symbols) and GET /watchlists + GET /watchlists/{id}/items (compact
 * per-symbol rows). The backend has no per-item price/score/change
 * field (watchlist/models.py::WatchlistItem), so rows show only what
 * actually exists - symbol, folder, favorite - never a fabricated
 * quote (WEB STEP 2 §7).
 */
export function WatchlistIntelligence() {
  const summary = useWatchlistDashboard()
  const watchlists = useWatchlists()
  const firstWatchlist = watchlists.data?.[0]
  const items = useWatchlistItems(firstWatchlist?.id ?? undefined)

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Watchlist intelligence</CardTitle>
          <CardSubtitle>Across all of your watchlists</CardSubtitle>
        </div>
        <Link to="/watchlist" className={styles.viewAll}>
          View all →
        </Link>
      </CardHeader>

      {summary.isLoading ? <SkeletonCard /> : null}
      {summary.isError ? <ErrorState message={apiErrorMessage(summary.error)} onRetry={() => void summary.refetch()} /> : null}

      {summary.data ? (
        summary.data.total_watchlists === 0 ? (
          <EmptyState title="No watchlists yet" description="Symbols you track will show up here." />
        ) : (
          <div className={styles.body}>
            <div className={styles.stats}>
              <span>
                <strong className="num">{summary.data.total_items}</strong> items
              </span>
              <span>
                <strong className="num">{summary.data.total_favorites}</strong> favorites
              </span>
            </div>

            {summary.data.most_tracked_symbols.length > 0 ? (
              <div className={styles.symbols}>
                {summary.data.most_tracked_symbols.slice(0, 8).map((symbol) => (
                  <Badge key={symbol} tone="neutral">
                    <span className="num">{symbol}</span>
                  </Badge>
                ))}
              </div>
            ) : null}

            <div className={styles.itemsSection}>
              {items.isLoading ? (
                <SkeletonCard />
              ) : items.data && items.data.length > 0 ? (
                <ul className={styles.itemList}>
                  {items.data.slice(0, 6).map((item) => (
                    <li key={item.id} className={styles.itemRow}>
                      <Link to={`/assets/${item.symbol}`} className={`num ${styles.symbol}`}>
                        {item.symbol}
                      </Link>
                      <span className={styles.folder}>{item.folder ?? '—'}</span>
                      {item.is_favorite ? <Badge tone="accent">★</Badge> : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </div>
        )
      ) : null}
    </Card>
  )
}
