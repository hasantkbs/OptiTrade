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
