import { useQuery, useQueryClient } from '@tanstack/react-query'
import { portfolioApi } from '../../api/endpoints'

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
