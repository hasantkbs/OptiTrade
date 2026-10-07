import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../components/ui/Button'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { SkeletonCard } from '../components/ui/Skeleton'
import { Table, TableCell, TableHeadCell } from '../components/ui/Table'
import { useWatchlistItems, useWatchlists } from '../features/dashboard/hooks'
import { AddSymbolDialog } from '../features/watchlist/AddSymbolDialog'
import { CreateWatchlistDialog } from '../features/watchlist/CreateWatchlistDialog'
import { apiErrorMessage } from '../api/client'

/**
 * Backed by GET /watchlists + GET /watchlists/{id}/items (watchlist/models.py).
 *
 * Only the empty state can open `CreateWatchlistDialog` - it creates the
 * user's one (and, today, only reachable) watchlist. There is no
 * watchlist selector anywhere in the app yet (every consumer - this
 * page, Asset Detail, Dashboard, Decisions - independently reads
 * `watchlists[0]`), so a second "New watchlist" entry point here would
 * create a watchlist nothing could ever show again - a genuine dead end,
 * not a supported multi-watchlist feature. Re-add a create action to
 * this branch once a real selector exists to make every watchlist
 * reachable, not before (multi-resource UX audit).
 */
export function WatchlistPage() {
  const [createOpen, setCreateOpen] = useState(false)
  const [addSymbolOpen, setAddSymbolOpen] = useState(false)
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
      <>
        <Card>
          <EmptyState
            title="No watchlists yet"
            description="Create a watchlist to track assets and decisions."
            action={
              <Button size="sm" onClick={() => setCreateOpen(true)}>
                Create watchlist
              </Button>
            }
          />
        </Card>
        <CreateWatchlistDialog open={createOpen} onClose={() => setCreateOpen(false)} />
      </>
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
          <Button size="sm" onClick={() => setAddSymbolOpen(true)}>
            + Add symbol
          </Button>
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
          <EmptyState
            title="No symbols yet"
            description="Open an asset and use “Add to watchlist” to track it here."
            action={<Link to="/assets">Browse assets</Link>}
          />
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
                <TableCell numeric>
                  <Link to={`/assets/${item.symbol}`}>{item.symbol}</Link>
                </TableCell>
                <TableCell>{item.folder ?? '—'}</TableCell>
                <TableCell align="right">
                  {item.is_favorite ? <Badge tone="accent">Favorite</Badge> : null}
                </TableCell>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      <AddSymbolDialog open={addSymbolOpen} watchlistId={first?.id ?? undefined} onClose={() => setAddSymbolOpen(false)} />
    </Card>
  )
}
