import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { MarketSnapshotPage } from './MarketSnapshotPage'
import { marketApi, dashboardApi } from '../api/endpoints'

vi.mock('../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/endpoints')>()
  return { ...actual, marketApi: { snapshot: vi.fn() }, dashboardApi: { ...actual.dashboardApi, market: vi.fn() } }
})

const mockedMarketApi = vi.mocked(marketApi)
const mockedDashboardApi = vi.mocked(dashboardApi)

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MarketSnapshotPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedDashboardApi.market.mockResolvedValue({
    regime_distribution: {}, volatility_map: {}, sector_heatmap: [], news_impact_summary: [], generated_at: '2026-01-01T00:00:00Z',
  })
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
})
