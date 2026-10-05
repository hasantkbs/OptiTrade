import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { chartApi, newsApi, priceApi, quantApi, watchlistApi } from '../../api/endpoints'
import type { AddWatchlistItemRequest, ChartPeriod } from '../../api/types'
import { useWatchlistItems, useWatchlists } from '../dashboard/hooks'

/**
 * Asset Explorer data hooks. GET /price and GET /chart are cheap, cacheable
 * reads (plain useQuery). POST /quant/analyze is rate-limited
 * (10/minute, main.py) and re-runs real engine work server-side each
 * call, so it is a useMutation the page triggers explicitly - never an
 * auto-refetching query (WEB STEP 4 §17-18). Watchlist membership reuses
 * the exact same `useWatchlists`/`useWatchlistItems` hooks the dashboard
 * and Watchlist page already use, so this page never issues a second,
 * duplicate fetch of either resource.
 */

const PRICE_STALE_MS = 20_000
const CHART_STALE_MS = 5 * 60_000
const NEWS_STALE_MS = 5 * 60_000

export function usePrice(symbol: string) {
  return useQuery({
    queryKey: ['asset', symbol, 'price'],
    queryFn: () => priceApi.get(symbol),
    staleTime: PRICE_STALE_MS,
  })
}

export function useChart(symbol: string, period: ChartPeriod) {
  return useQuery({
    queryKey: ['asset', symbol, 'chart', period],
    queryFn: () => chartApi.get(symbol, period),
    staleTime: CHART_STALE_MS,
  })
}

export function useQuantAnalyze(symbol: string) {
  return useMutation({
    mutationFn: () => quantApi.analyze(symbol),
  })
}

export function useAssetNews(symbol: string) {
  return useQuery({
    queryKey: ['asset', symbol, 'news'],
    queryFn: () => newsApi.get(symbol),
    staleTime: NEWS_STALE_MS,
  })
}

/**
 * Watchlist membership + add/remove for one symbol, scoped to the
 * user's first watchlist - the same "first watchlist" convention the
 * Watchlist page and dashboard already use (see WatchlistPage.tsx), not
 * a new multi-watchlist picker.
 */
export function useAssetWatchlistState(symbol: string) {
  const queryClient = useQueryClient()
  const watchlists = useWatchlists()
  const firstWatchlist = watchlists.data?.[0]
  const items = useWatchlistItems(firstWatchlist?.id ?? undefined)

  const matchingItem = items.data?.find((item) => item.symbol.toUpperCase() === symbol.toUpperCase())

  function invalidateItems() {
    if (firstWatchlist?.id != null) {
      void queryClient.invalidateQueries({ queryKey: ['watchlists', firstWatchlist.id, 'items'] })
    }
    void queryClient.invalidateQueries({ queryKey: ['dashboard', 'watchlists'] })
  }

  const addMutation = useMutation({
    mutationFn: (body: AddWatchlistItemRequest) => watchlistApi.addItem(firstWatchlist!.id as number, body),
    onSuccess: invalidateItems,
  })

  const removeMutation = useMutation({
    mutationFn: () => watchlistApi.removeItem(firstWatchlist!.id as number, symbol),
    onSuccess: invalidateItems,
  })

  return {
    hasWatchlist: Boolean(firstWatchlist),
    isInWatchlist: Boolean(matchingItem),
    isLoading: watchlists.isLoading || (firstWatchlist != null && items.isLoading),
    isMutating: addMutation.isPending || removeMutation.isPending,
    add: () => addMutation.mutate({ symbol }),
    remove: () => removeMutation.mutate(),
  }
}
