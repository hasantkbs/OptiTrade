import { Card, CardHeader, CardSubtitle, CardTitle } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { SkeletonCard } from '../components/ui/Skeleton'
import { Table, TableCell, TableHeadCell } from '../components/ui/Table'
import { useWatchlistItems, useWatchlists } from '../features/dashboard/hooks'
import { apiErrorMessage } from '../api/client'

/** Backed by GET /watchlists + GET /watchlists/{id}/items (watchlist/models.py). */
export function WatchlistPage() {
  const watchlists = useWatchlists()
  const first = watchlists.data?.[0]
  const items = useWatchlistItems(first?.id ?? undefined)

  if (watchlists.isLoading) {
    return (
      <Card>
        <SkeletonCard />
      </Card>
    )
  }

  if (watchlists.isError) {
    return (
      <Card>
        <ErrorState message={apiErrorMessage(watchlists.error)} onRetry={() => void watchlists.refetch()} />
      </Card>
    )
  }

  if (!watchlists.data || watchlists.data.length === 0) {
    return (
      <Card>
        <EmptyState title="No watchlists yet" description="Watchlists you create will appear here." />
      </Card>
    )
  }

  return (
    <Card padding="none">
      <div style={{ padding: 'var(--space-5)', paddingBottom: 0 }}>
        <CardHeader>
          <div>
            <CardTitle>{first?.name}</CardTitle>
            <CardSubtitle>Tracked symbols</CardSubtitle>
          </div>
        </CardHeader>
      </div>

      {items.isLoading ? (
        <div style={{ padding: 'var(--space-5)' }}>
          <SkeletonCard />
        </div>
      ) : items.isError ? (
        <div style={{ padding: 'var(--space-5)' }}>
          <ErrorState message={apiErrorMessage(items.error)} onRetry={() => void items.refetch()} />
        </div>
      ) : !items.data || items.data.length === 0 ? (
        <div style={{ padding: 'var(--space-5)' }}>
          <EmptyState title="No symbols yet" description="Symbols added to this watchlist will appear here." />
        </div>
      ) : (
        <Table>
          <thead>
            <tr>
              <TableHeadCell>Symbol</TableHeadCell>
              <TableHeadCell>Folder</TableHeadCell>
              <TableHeadCell align="right">Favorite</TableHeadCell>
            </tr>
          </thead>
          <tbody>
            {items.data.map((item) => (
              <tr key={item.id}>
                <TableCell numeric>{item.symbol}</TableCell>
                <TableCell>{item.folder ?? '—'}</TableCell>
                <TableCell align="right">
                  {item.is_favorite ? <Badge tone="accent">Favorite</Badge> : null}
                </TableCell>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  )
}
