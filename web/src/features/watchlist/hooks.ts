import { useMutation, useQueryClient } from '@tanstack/react-query'
import { watchlistApi } from '../../api/endpoints'
import type { CreateWatchlistRequest } from '../../api/types'

/**
 * POST /watchlists (watchlist/models.py::CreateWatchlistRequest) - takes
 * only `name`, a watchlist may be created empty (no items endpoint is
 * required at creation time), and there is no uniqueness constraint on
 * name (confirmed against watchlist_service.py directly). Invalidates
 * `['watchlists']`, the same key `useWatchlists` (features/dashboard/
 * hooks.ts) reads - both the Watchlist page and the dashboard's
 * WatchlistIntelligence card pick up the new watchlist without a manual
 * refresh.
 */
export function useCreateWatchlist() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CreateWatchlistRequest) => watchlistApi.create(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['watchlists'] })
    },
  })
}
