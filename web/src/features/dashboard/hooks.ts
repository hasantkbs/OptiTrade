import { useQuery, useQueryClient } from '@tanstack/react-query'
import { alertsApi, dashboardApi, marketApi, portfolioApi, watchlistApi } from '../../api/endpoints'

/**
 * One hook per dashboard data need, each a thin wrapper over the
 * matching api/endpoints.ts function - UI components call these, never
 * the API client directly. Query keys are namespaced per resource so a
 * mutation elsewhere (a later step) can invalidate precisely, and so
 * the exact same resource requested from two different components
 * (e.g. the dashboard's portfolio summary and the standalone Portfolio
 * page) shares one cached fetch instead of firing twice.
 *
 * staleTime is set per-resource, not globally (WEB STEP 2 §15): each
 * reflects how often that specific backend value actually changes -
 * see dashboard/scheduler.py for what the backend itself recomputes on
 * a schedule vs. computes fresh per-request. None of these poll -
 * nothing here justifies unsolicited background refetching.
 */

const STALE = {
  /** dashboard/scheduler.py recomputes overview/market/engine views on
   * its own schedule - refetching more often than that just re-reads
   * the same cached value from the backend. */
  scheduled: 60_000,
  /** Configuration-shaped resources (watchlists, portfolios) that only
   * change when the user acts, not on a timer. */
  config: 45_000,
  /** Alerts are the most time-sensitive resource on the dashboard -
   * shorter staleness so a just-fired alert shows up promptly. */
  alerts: 20_000,
} as const

export function useOverview() {
  return useQuery({ queryKey: ['dashboard', 'overview'], queryFn: dashboardApi.overview, staleTime: STALE.scheduled })
}

export function useEngineDashboard() {
  return useQuery({
    queryKey: ['dashboard', 'engines'],
    queryFn: () => dashboardApi.engines(),
    staleTime: STALE.scheduled,
  })
}

export function useWatchlistDashboard() {
  return useQuery({
    queryKey: ['dashboard', 'watchlists'],
    queryFn: dashboardApi.watchlists,
    staleTime: STALE.config,
  })
}

export function useAlertDashboard() {
  return useQuery({ queryKey: ['dashboard', 'alerts'], queryFn: dashboardApi.alerts, staleTime: STALE.alerts })
}

export function useMarketDashboard(market = 'US') {
  return useQuery({
    queryKey: ['dashboard', 'market', market],
    queryFn: () => dashboardApi.market(market),
    staleTime: STALE.scheduled,
  })
}

export function useLearningDashboard() {
  return useQuery({
    queryKey: ['dashboard', 'learning'],
    queryFn: dashboardApi.learning,
    staleTime: STALE.scheduled,
  })
}

export function usePortfolioList() {
  return useQuery({ queryKey: ['portfolios'], queryFn: portfolioApi.list, staleTime: STALE.config })
}

export function usePortfolioDashboard(portfolioId: number | undefined) {
  return useQuery({
    queryKey: ['dashboard', 'portfolio', portfolioId],
    queryFn: () => dashboardApi.portfolio(portfolioId as number),
    enabled: portfolioId !== undefined,
    staleTime: STALE.config,
  })
}

export function useWatchlists() {
  return useQuery({ queryKey: ['watchlists'], queryFn: watchlistApi.list, staleTime: STALE.config })
}

export function useWatchlistItems(watchlistId: number | undefined) {
  return useQuery({
    queryKey: ['watchlists', watchlistId, 'items'],
    queryFn: () => watchlistApi.items(watchlistId as number),
    enabled: watchlistId !== undefined,
    staleTime: STALE.config,
  })
}

export function useAlerts() {
  return useQuery({ queryKey: ['alerts'], queryFn: alertsApi.list, staleTime: STALE.alerts })
}

export function useMarketSnapshot() {
  return useQuery({ queryKey: ['dashboard', 'market-snapshot'], queryFn: marketApi.snapshot, staleTime: STALE.scheduled })
}

/**
 * Whole-dashboard refresh (WEB STEP 2 §11): invalidates every query
 * key this feature owns rather than each section wiring its own
 * refetch button to its own query - one real, visible action instead
 * of several uncoordinated ones.
 */
export function useRefreshDashboard() {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    void queryClient.invalidateQueries({ queryKey: ['portfolios'] })
    void queryClient.invalidateQueries({ queryKey: ['watchlists'] })
    void queryClient.invalidateQueries({ queryKey: ['alerts'] })
  }
}
