import { useQuery } from '@tanstack/react-query'
import { marketApi } from '../../api/endpoints'

export type SearchableMarket = 'TR' | 'US' | 'CRYPTO'

export interface SearchableSymbol {
  symbol: string
  name: string
  market: SearchableMarket
}

const MARKETS: SearchableMarket[] = ['TR', 'US', 'CRYPTO']

/**
 * Backed by GET /market/watchlist/{market} (core/market_config.py) - an
 * existing endpoint that already returns each market's full symbol list
 * pre-suffixed correctly (BIST tickers carry .IS), never called from the
 * frontend before this. Fetching all three markets once and merging them
 * client-side is simpler than a server-side search endpoint for a ~80-
 * symbol universe that changes essentially never.
 */
export function useMarketSymbols() {
  return useQuery({
    queryKey: ['market', 'symbols'],
    queryFn: async () => {
      const responses = await Promise.all(MARKETS.map((market) => marketApi.watchlist(market)))
      const merged: SearchableSymbol[] = []
      responses.forEach((response, index) => {
        const market = MARKETS[index]
        Object.entries(response.symbols).forEach(([symbol, name]) => {
          merged.push({ symbol, name, market })
        })
      })
      return merged
    },
    staleTime: 10 * 60_000,
  })
}

/**
 * Backed by GET /market/opportunities/{market} (intelligence.
 * opportunity_ranking - Phase C scan + Phase D ranking) - the backend's
 * own market_opportunities_refresh_loop recomputes this every 5 minutes,
 * so refetchInterval here matches that cadence rather than polling
 * faster than the data could ever actually change. A cold cache (no
 * scan has completed yet, e.g. right after a deploy) is a 503, not an
 * error to retry aggressively for - the default retry count is enough.
 */
export function useMarketOpportunities(market: SearchableMarket) {
  return useQuery({
    queryKey: ['market', 'opportunities', market],
    queryFn: () => marketApi.opportunities(market),
    refetchInterval: 5 * 60_000,
    staleTime: 4 * 60_000,
  })
}
