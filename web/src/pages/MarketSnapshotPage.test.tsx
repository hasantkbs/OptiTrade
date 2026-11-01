import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { MarketSnapshotPage } from './MarketSnapshotPage'
import { marketApi, dashboardApi } from '../api/endpoints'

vi.mock('../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/endpoints')>()
  return {
    ...actual,
    marketApi: { snapshot: vi.fn(), watchlist: vi.fn(), opportunities: vi.fn() },
    dashboardApi: { ...actual.dashboardApi, market: vi.fn() },
  }
})

const mockedMarketApi = vi.mocked(marketApi)
const mockedDashboardApi = vi.mocked(dashboardApi)

const marketInfo = {
  name: 'x', flag: 'x', currency: 'x', timezone: 'x', session_open: 'x', session_close: 'x',
  index_symbol: 'x', index_name: 'x', description: 'x',
}

function DestinationStub() {
  const { symbol } = useParams()
  return <div>Asset detail for {symbol}</div>
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<MarketSnapshotPage />} />
          <Route path="/assets/:symbol" element={<DestinationStub />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedDashboardApi.market.mockResolvedValue({
    regime_distribution: {}, volatility_map: {}, sector_heatmap: [], news_impact_summary: [], generated_at: '2026-01-01T00:00:00Z',
  })
  mockedMarketApi.watchlist.mockImplementation((market: string) =>
    Promise.resolve({
      market,
      info: marketInfo,
      watchlist: [],
      symbols: (market === 'TR' ? { 'GARAN.IS': 'Garanti BBVA' } : {}) as Record<string, string>,
    }),
  )
  mockedMarketApi.opportunities.mockImplementation((market: string) =>
    Promise.resolve({
      market, opportunities: [], total_scanned_count: 0, failed_count: 0,
      generated_at: '2026-01-01T00:00:00Z',
    }),
  )
})

describe('MarketSnapshotPage', () => {
  it('renders both index charts and the dominance figure', async () => {
    mockedMarketApi.snapshot.mockResolvedValueOnce({
      bist100: { symbol: 'XU100.IS', period: '3mo', change_pct: 1.1, high: 100, low: 90, points: [] },
      btc: { symbol: 'BTC-USD', period: '3mo', change_pct: 2.2, high: 70000, low: 60000, points: [] },
      btc_dominance_pct: 54.3,
      generated_at: '2026-01-01T00:00:00Z',
    })
    renderPage()
    await waitFor(() => expect(screen.getByText('54.3%')).toBeInTheDocument())
    expect(screen.getByText('BTC Dominance')).toBeInTheDocument()
  })

  it('searches and navigates to a canonical, correctly-suffixed symbol', async () => {
    const user = userEvent.setup()
    mockedMarketApi.snapshot.mockResolvedValueOnce({
      bist100: { symbol: 'XU100.IS', period: '3mo', change_pct: 1.1, high: 100, low: 90, points: [] },
      btc: { symbol: 'BTC-USD', period: '3mo', change_pct: 2.2, high: 70000, low: 60000, points: [] },
      btc_dominance_pct: 54.3,
      generated_at: '2026-01-01T00:00:00Z',
    })
    renderPage()

    await user.type(screen.getByLabelText('Look up a stock or crypto'), 'GARAN')
    await user.click(await screen.findByRole('button', { name: /GARAN.IS/ }))

    await waitFor(() => expect(screen.getByText('Asset detail for GARAN.IS')).toBeInTheDocument())
  })

  it('shows the Top opportunities picker with a tab for each supported market', async () => {
    mockedMarketApi.snapshot.mockResolvedValueOnce({
      bist100: { symbol: 'XU100.IS', period: '3mo', change_pct: 1.1, high: 100, low: 90, points: [] },
      btc: { symbol: 'BTC-USD', period: '3mo', change_pct: 2.2, high: 70000, low: 60000, points: [] },
      btc_dominance_pct: 54.3,
      generated_at: '2026-01-01T00:00:00Z',
    })
    renderPage()

    expect(await screen.findByText('Top opportunities')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'BIST (TR)' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'US' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Crypto' })).toBeInTheDocument()
  })
})
