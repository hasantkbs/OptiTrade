import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AxiosError } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AssetDetailPage } from './AssetDetailPage'
import { chartApi, priceApi, quantApi, watchlistApi, newsApi } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  priceApi: { get: vi.fn() },
  chartApi: { get: vi.fn() },
  quantApi: { analyze: vi.fn() },
  watchlistApi: { list: vi.fn(), items: vi.fn(), addItem: vi.fn(), removeItem: vi.fn() },
  newsApi: { get: vi.fn() },
}))

const mockedPriceApi = vi.mocked(priceApi)
const mockedChartApi = vi.mocked(chartApi)
const mockedQuantApi = vi.mocked(quantApi)
const mockedWatchlistApi = vi.mocked(watchlistApi)
const mockedNewsApi = vi.mocked(newsApi)

function renderPage(initialPath = '/assets/AAPL') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/assets/:symbol" element={<AssetDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const priceQuote = { symbol: 'AAPL', price: 189.5, change_pct: 1.25, timestamp: '2026-01-01T20:00:00Z' }
const chartResponse = {
  symbol: 'AAPL',
  period: '3mo',
  points: [{ date: '2026-01-01', close: 180, volume: 1_000_000, rsi: null }],
  change_pct: 2.5,
  high: 190,
  low: 178,
}
const pipelineResponse = {
  symbol: 'AAPL',
  decision: 'BUY' as const,
  confidence: 0.72,
  expected_return: 0.034,
  expected_volatility: 0.18,
  engine_breakdown: [],
  evidence: [],
  risk: { risk_level: 'MEDIUM', expected_volatility: 0.18, data_sufficiency: 0.9 },
  explanation: 'Technical momentum outweighs neutral fundamentals.',
  metadata: {
    pipeline_version: '1.0.0',
    total_duration_ms: 120,
    stage_durations_ms: {},
    engines_available: 3,
    engines_succeeded: 3,
    degraded: false,
    timestamp: '2026-01-01T20:00:00Z',
  },
}
const watchlist = { id: 1, owner: 'user-1', name: 'Core', created_at: '2026-01-01T00:00:00Z' }
const newsResponse = {
  symbol: 'AAPL', sector: 'Technology', market: 'US', total_news: 0, analyzed_news: 0,
  sentiment_score: 0, sentiment_label: 'Neutral', score_delta: 0, positive_count: 0,
  negative_count: 0, neutral_count: 0, signals: [], top_positive_title: null, top_negative_title: null,
  fetched_at: '2026-01-01T00:00:00Z', headlines: [], error: null,
}

function notFound() {
  const error = new AxiosError('Not Found')
  error.response = { status: 404, data: { detail: 'AAPL fiyati bulunamadi.' }, statusText: 'Not Found', headers: {}, config: {} as never }
  return error
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedChartApi.get.mockResolvedValue(chartResponse)
  mockedQuantApi.analyze.mockResolvedValue(pipelineResponse)
  mockedWatchlistApi.list.mockResolvedValue([watchlist])
  mockedWatchlistApi.items.mockResolvedValue([])
  mockedNewsApi.get.mockResolvedValue(newsResponse)
})

describe('AssetDetailPage', () => {
  it('reads the symbol from the URL and renders real price data', async () => {
    mockedPriceApi.get.mockResolvedValueOnce(priceQuote)
    renderPage('/assets/AAPL')
    await waitFor(() => expect(screen.getByText('189.5')).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: 'AAPL' })).toBeInTheDocument()
    expect(mockedPriceApi.get).toHaveBeenCalledWith('AAPL')
  })

  it('shows an honest "not found" state for an invalid symbol and never spends the rate-limited analysis call on it', async () => {
    mockedPriceApi.get.mockRejectedValueOnce(notFound())
    renderPage('/assets/NOPE')
    await waitFor(() => expect(screen.getByText('"NOPE" not found')).toBeInTheDocument())
    expect(mockedQuantApi.analyze).not.toHaveBeenCalled()
  })

  it('shows a retryable price error without blocking the rest of the page', async () => {
    mockedPriceApi.get.mockRejectedValueOnce(new Error('network down'))
    renderPage('/assets/AAPL')
    await waitFor(() => expect(screen.getByText('Something went wrong. Please try again.')).toBeInTheDocument())
    // Price failing (a transient/network error, not a 404) does not stop the
    // rest of the page from rendering and analyzing independently.
    expect(screen.getByText('Price history')).toBeInTheDocument()
    expect(mockedQuantApi.analyze).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Analyze' })).toBeInTheDocument()
  })

  it('auto-runs the quant analysis exactly once when the symbol first loads successfully', async () => {
    mockedPriceApi.get.mockResolvedValue(priceQuote)
    renderPage('/assets/AAPL')
    await waitFor(() => expect(screen.getByText('BUY')).toBeInTheDocument())
    expect(mockedQuantApi.analyze).toHaveBeenCalledTimes(1)
  })

  it('re-runs analysis only when "Refresh analysis" is explicitly clicked', async () => {
    const user = userEvent.setup()
    mockedPriceApi.get.mockResolvedValue(priceQuote)
    renderPage('/assets/AAPL')
    await waitFor(() => expect(screen.getByText('BUY')).toBeInTheDocument())
    expect(mockedQuantApi.analyze).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('button', { name: 'Refresh analysis' }))
    await waitFor(() => expect(mockedQuantApi.analyze).toHaveBeenCalledTimes(2))
  })

  it('Refresh re-fetches price and chart', async () => {
    const user = userEvent.setup()
    mockedPriceApi.get.mockResolvedValue(priceQuote)
    renderPage('/assets/AAPL')
    await waitFor(() => expect(screen.getByText('189.5')).toBeInTheDocument())

    const priceCallsBefore = mockedPriceApi.get.mock.calls.length
    const chartCallsBefore = mockedChartApi.get.mock.calls.length
    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    await waitFor(() => expect(mockedPriceApi.get.mock.calls.length).toBeGreaterThan(priceCallsBefore))
    expect(mockedChartApi.get.mock.calls.length).toBeGreaterThan(chartCallsBefore)
  })

  it('reflects real watchlist membership and lets the user add the symbol, refreshing state afterward', async () => {
    const user = userEvent.setup()
    mockedPriceApi.get.mockResolvedValue(priceQuote)
    mockedWatchlistApi.items
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        { id: 1, watchlist_id: 1, symbol: 'AAPL', is_favorite: false, folder: null, tags: [], notes: '', added_at: '2026-01-01T00:00:00Z' },
      ])
    mockedWatchlistApi.addItem.mockResolvedValueOnce({
      id: 1,
      watchlist_id: 1,
      symbol: 'AAPL',
      is_favorite: false,
      folder: null,
      tags: [],
      notes: '',
      added_at: '2026-01-01T00:00:00Z',
    })
    renderPage('/assets/AAPL')

    await waitFor(() => expect(screen.getByRole('button', { name: 'Add to watchlist' })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Add to watchlist' }))

    expect(mockedWatchlistApi.addItem).toHaveBeenCalledWith(1, { symbol: 'AAPL' })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Remove from watchlist' })).toBeInTheDocument())
  })
})
