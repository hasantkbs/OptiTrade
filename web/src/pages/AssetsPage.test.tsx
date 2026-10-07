import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AssetsPage } from './AssetsPage'
import { dashboardApi, marketApi } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  dashboardApi: { market: vi.fn() },
  marketApi: { watchlist: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)
const mockedMarketApi = vi.mocked(marketApi)

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
      <MemoryRouter initialEntries={['/assets']}>
        <Routes>
          <Route path="/assets" element={<AssetsPage />} />
          <Route path="/assets/:symbol" element={<DestinationStub />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedMarketApi.watchlist.mockImplementation((market: string) =>
    Promise.resolve({
      market,
      info: marketInfo,
      watchlist: [],
      symbols: (market === 'TR' ? { 'GARAN.IS': 'Garanti BBVA' } : {}) as Record<string, string>,
    }),
  )
})

describe('AssetsPage', () => {
  it('shows the sector table with explanatory, non-jargon column headers', async () => {
    mockedDashboardApi.market.mockResolvedValueOnce({
      regime_distribution: {}, volatility_map: {},
      sector_heatmap: [{ sector: 'TECH', opportunity_score: 72.3, avg_change_pct: 1.5, trend: 'BULLISH' }],
      news_impact_summary: [], generated_at: '2026-01-01T00:00:00Z',
    })
    renderPage()

    expect(await screen.findByText('Opportunity score (0-100)')).toBeInTheDocument()
    expect(screen.getByText('Avg daily change')).toBeInTheDocument()
  })

  it('searches and navigates to a canonical, correctly-suffixed symbol', async () => {
    const user = userEvent.setup()
    mockedDashboardApi.market.mockResolvedValueOnce({
      regime_distribution: {}, volatility_map: {}, sector_heatmap: [], news_impact_summary: [],
      generated_at: '2026-01-01T00:00:00Z',
    })
    renderPage()

    await user.type(screen.getByLabelText('Look up a stock or crypto'), 'GARAN')
    await user.click(await screen.findByRole('button', { name: /GARAN.IS/ }))

    await waitFor(() => expect(screen.getByText('Asset detail for GARAN.IS')).toBeInTheDocument())
  })
})
