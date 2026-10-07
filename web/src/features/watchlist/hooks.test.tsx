import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { useAddWatchlistItem } from './hooks'
import { watchlistApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/endpoints')>()
  return { ...actual, watchlistApi: { ...actual.watchlistApi, addItem: vi.fn() } }
})

const mockedWatchlistApi = vi.mocked(watchlistApi)

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

const item = {
  id: 1, watchlist_id: 7, symbol: 'AAPL', is_favorite: false, folder: null, tags: [], notes: '',
  added_at: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useAddWatchlistItem', () => {
  it('adds a symbol via the real POST /watchlists/{id}/items contract', async () => {
    mockedWatchlistApi.addItem.mockResolvedValueOnce(item)
    const { result } = renderHook(() => useAddWatchlistItem(7), { wrapper })

    result.current.mutate('AAPL')

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(mockedWatchlistApi.addItem).toHaveBeenCalledWith(7, { symbol: 'AAPL' })
  })
})
