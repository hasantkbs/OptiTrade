import { useQuery } from '@tanstack/react-query'
import { alertsApi, dashboardApi, portfolioApi, watchlistApi } from '../../api/endpoints'

/**
 * One hook per dashboard data need, each a thin wrapper over the
 * matching api/endpoints.ts function - UI components call these, never
 * the API client directly. Query keys are namespaced per resource so a
 * mutation elsewhere (a later step) can invalidate precisely.
 */

export function useOverview() {
  return useQuery({ queryKey: ['dashboard', 'overview'], queryFn: dashboardApi.overview })
}

export function useEngineDashboard() {
  return useQuery({ queryKey: ['dashboard', 'engines'], queryFn: () => dashboardApi.engines() })
}

export function useWatchlistDashboard() {
  return useQuery({ queryKey: ['dashboard', 'watchlists'], queryFn: dashboardApi.watchlists })
}

export function useAlertDashboard() {
  return useQuery({ queryKey: ['dashboard', 'alerts'], queryFn: dashboardApi.alerts })
}

export function useMarketDashboard(market = 'US') {
  return useQuery({ queryKey: ['dashboard', 'market', market], queryFn: () => dashboardApi.market(market) })
}

export function useLearningDashboard() {
  return useQuery({ queryKey: ['dashboard', 'learning'], queryFn: dashboardApi.learning })
}

export function usePortfolioList() {
  return useQuery({ queryKey: ['portfolios'], queryFn: portfolioApi.list })
}

export function usePortfolioDashboard(portfolioId: number | undefined) {
  return useQuery({
    queryKey: ['dashboard', 'portfolio', portfolioId],
    queryFn: () => dashboardApi.portfolio(portfolioId as number),
    enabled: portfolioId !== undefined,
  })
}

export function useWatchlists() {
  return useQuery({ queryKey: ['watchlists'], queryFn: watchlistApi.list })
}

export function useWatchlistItems(watchlistId: number | undefined) {
  return useQuery({
    queryKey: ['watchlists', watchlistId, 'items'],
    queryFn: () => watchlistApi.items(watchlistId as number),
    enabled: watchlistId !== undefined,
  })
}

export function useAlerts() {
  return useQuery({ queryKey: ['alerts'], queryFn: alertsApi.list })
}
