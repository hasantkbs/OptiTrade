import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { useMarketOpportunities, useMarketSymbols } from './hooks'
import { marketApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/endpoints')>()
  return { ...actual, marketApi: { ...actual.marketApi, watchlist: vi.fn(), opportunities: vi.fn() } }
})

const mockedMarketApi = vi.mocked(marketApi)

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

const info = {
  name: 'x', flag: 'x', currency: 'x', timezone: 'x', session_open: 'x', session_close: 'x',
  index_symbol: 'x', index_name: 'x', description: 'x',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useMarketSymbols', () => {
  it('merges all three markets into one flat, correctly-suffixed symbol list', async () => {
    mockedMarketApi.watchlist.mockImplementation((market: string) =>
      Promise.resolve({
        market,
        info,
        watchlist: [],
        symbols: (
          market === 'TR'
            ? { 'GARAN.IS': 'Garanti BBVA' }
            : market === 'US'
              ? { AAPL: 'Apple' }
              : { 'BTC-USD': 'Bitcoin' }
        ) as Record<string, string>,
      }),
    )

    const { result } = renderHook(() => useMarketSymbols(), { wrapper })

    await waitFor(() => expect(result.current.data).toHaveLength(3))
    expect(result.current.data).toEqual(
      expect.arrayContaining([
        { symbol: 'GARAN.IS', name: 'Garanti BBVA', market: 'TR' },
        { symbol: 'AAPL', name: 'Apple', market: 'US' },
        { symbol: 'BTC-USD', name: 'Bitcoin', market: 'CRYPTO' },
      ]),
    )
  })
})

describe('useMarketOpportunities', () => {
  it('fetches the ranked opportunities for the given market', async () => {
    mockedMarketApi.opportunities.mockResolvedValueOnce({
      market: 'US',
      opportunities: [
        {
          rank: 1, symbol: 'AAPL', decision: 'BUY', label: 'BUY_BIAS', confidence: 0.7,
          expected_return: 0.03, expected_volatility: 0.15, risk_bucket: 'MEDIUM',
        },
      ],
      total_scanned_count: 28, failed_count: 0, generated_at: '2026-01-01T00:00:00Z',
    })

    const { result } = renderHook(() => useMarketOpportunities('US'), { wrapper })

    await waitFor(() => expect(result.current.data?.opportunities).toHaveLength(1))
    expect(mockedMarketApi.opportunities).toHaveBeenCalledWith('US')
  })
})
