import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { portfolioApi } from '../../api/endpoints'
import type { CreatePortfolioRequest, TradeRequest } from '../../api/types'

/**
 * Portfolio-page-specific data hooks. `usePortfolioList` and
 * `usePortfolioDashboard` (the two resources this page shares with the
 * dashboard) live in features/dashboard/hooks.ts and are reused as-is
 * here - same query keys, so switching between the dashboard and this
 * page never triggers a duplicate fetch of either resource.
 */

const TRANSACTIONS_STALE_MS = 45_000

export function usePortfolioTransactions(portfolioId: number | undefined, symbol?: string) {
  return useQuery({
    queryKey: ['portfolios', portfolioId, 'transactions', symbol ?? null],
    queryFn: () => portfolioApi.transactions(portfolioId as number, symbol),
    enabled: portfolioId !== undefined,
    staleTime: TRANSACTIONS_STALE_MS,
  })
}

/** POST /portfolios (portfolio/models.py::CreatePortfolioRequest) - a
 * user may hold any number of portfolios, there is no uniqueness
 * constraint on name, and no default portfolio is created for a new
 * account (confirmed against the backend service/repository directly).
 * Invalidates `['portfolios']` only, matching `useCreateAlert`'s own
 * scoped-invalidation convention - the newly created portfolio needs no
 * dashboard/transactions data yet. */
export function useCreatePortfolio() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CreatePortfolioRequest) => portfolioApi.create(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['portfolios'] })
    },
  })
}

/** POST /portfolios/{id}/buy (portfolio/service.py's PortfolioService.buy)
 * - records one real BUY transaction; the backend replays the whole
 * ledger to derive the resulting position/average-cost/P&L, never
 * computed here. There is no separate positions query to invalidate:
 * `usePortfolioDashboard`'s `['dashboard', 'portfolio', portfolioId]`
 * already carries `positions` (GET /dashboard/portfolios/{id} embeds
 * exactly the same PositionAnalytics the standalone GET /portfolios/
 * {id}/positions would return - see PortfolioDashboardService.build) -
 * invalidating it is what refreshes the Positions table. Transaction
 * history is invalidated separately since it's a distinct query. */
export function useAddPosition(portfolioId: number | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TradeRequest) => portfolioApi.buy(portfolioId as number, body),
    onSuccess: () => {
      if (portfolioId === undefined) return
      void queryClient.invalidateQueries({ queryKey: ['dashboard', 'portfolio', portfolioId] })
      void queryClient.invalidateQueries({ queryKey: ['portfolios', portfolioId, 'transactions'] })
    },
  })
}

/** Refreshes everything the Portfolio page reads for one portfolio - the
 * list (in case metadata changed), its dashboard, and its transactions. */
export function useRefreshPortfolio(portfolioId: number | undefined) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['portfolios'] })
    if (portfolioId !== undefined) {
      void queryClient.invalidateQueries({ queryKey: ['dashboard', 'portfolio', portfolioId] })
      void queryClient.invalidateQueries({ queryKey: ['portfolios', portfolioId, 'transactions'] })
    }
  }
}
