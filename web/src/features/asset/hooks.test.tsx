import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { useAssetNews } from './hooks'
import { newsApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/endpoints')>()
  return { ...actual, newsApi: { get: vi.fn() } }
})

const mockedNewsApi = vi.mocked(newsApi)

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useAssetNews', () => {
  it('fetches news for the given symbol', async () => {
    mockedNewsApi.get.mockResolvedValueOnce({
      symbol: 'AAPL', sector: 'Technology', market: 'US', total_news: 1, analyzed_news: 1,
      sentiment_score: 0.5, sentiment_label: 'Positive', score_delta: 0, positive_count: 1,
      negative_count: 0, neutral_count: 0, signals: [], top_positive_title: 'Good news',
      top_negative_title: null, fetched_at: '2026-01-01T00:00:00Z',
      headlines: [{ title: 'Good news', sentiment: 'Positive', score: 0.5, age_weight: 1, keywords: [], published_at: '2026-01-01T00:00:00Z' }],
      error: null,
    })
    const { result } = renderHook(() => useAssetNews('AAPL'), { wrapper })
    await waitFor(() => expect(result.current.data?.headlines).toHaveLength(1))
  })
})
