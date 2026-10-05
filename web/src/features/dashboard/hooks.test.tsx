import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { useMarketSnapshot } from './hooks'
import { marketApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/endpoints')>()
  return { ...actual, marketApi: { snapshot: vi.fn() } }
})

const mockedMarketApi = vi.mocked(marketApi)

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useMarketSnapshot', () => {
  it('fetches the market snapshot', async () => {
    mockedMarketApi.snapshot.mockResolvedValueOnce({
      bist100: null, btc: null, btc_dominance_pct: 54.1, generated_at: '2026-01-01T00:00:00Z',
    })
    const { result } = renderHook(() => useMarketSnapshot(), { wrapper })
    await waitFor(() => expect(result.current.data?.btc_dominance_pct).toBe(54.1))
  })
})
