import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WatchlistIntelligence } from './WatchlistIntelligence'
import { dashboardApi, watchlistApi } from '../../../api/endpoints'

vi.mock('../../../api/endpoints', () => ({
  dashboardApi: { watchlists: vi.fn() },
  watchlistApi: { list: vi.fn(), items: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)
const mockedWatchlistApi = vi.mocked(watchlistApi)

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <WatchlistIntelligence />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const summary = {
  total_watchlists: 1,
  total_items: 12,
  total_favorites: 3,
  most_tracked_symbols: ['AAPL', 'MSFT'],
  items_by_folder: { Core: 8, Speculative: 4 },
  generated_at: '2026-01-01T00:00:00Z',
}

const watchlist = { id: 1, owner: 'user-1', name: 'Core', created_at: '2026-01-01T00:00:00Z' }

const items = [
  { id: 1, watchlist_id: 1, symbol: 'AAPL', is_favorite: true, folder: 'Core', tags: [], notes: '', added_at: '2026-01-01T00:00:00Z' },
  { id: 2, watchlist_id: 1, symbol: 'MSFT', is_favorite: false, folder: 'Core', tags: [], notes: '', added_at: '2026-01-01T00:00:00Z' },
]

beforeEach(() => {
  vi.clearAllMocks()
})

describe('WatchlistIntelligence', () => {
  it('shows an honest empty state when there are no watchlists', async () => {
    mockedDashboardApi.watchlists.mockResolvedValueOnce({ ...summary, total_watchlists: 0, total_items: 0, total_favorites: 0, most_tracked_symbols: [] })
    mockedWatchlistApi.list.mockResolvedValueOnce([])
    renderWithClient()
    await waitFor(() => expect(screen.getByText('No watchlists yet')).toBeInTheDocument())
  })

  it('renders real summary counts and compact item rows without fabricating price or score', async () => {
    mockedDashboardApi.watchlists.mockResolvedValueOnce(summary)
    mockedWatchlistApi.list.mockResolvedValueOnce([watchlist])
    mockedWatchlistApi.items.mockResolvedValueOnce(items)
    renderWithClient()
    await waitFor(() => expect(screen.getByText('12')).toBeInTheDocument())
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getAllByText('AAPL').length).toBeGreaterThan(0)
    expect(screen.getByText('MSFT')).toBeInTheDocument()
    expect(screen.queryByText(/\$/)).not.toBeInTheDocument()
  })

  it('links to the full Watchlist page', async () => {
    mockedDashboardApi.watchlists.mockResolvedValueOnce(summary)
    mockedWatchlistApi.list.mockResolvedValueOnce([watchlist])
    mockedWatchlistApi.items.mockResolvedValueOnce(items)
    renderWithClient()
    await waitFor(() => expect(screen.getByRole('link', { name: /View all/ })).toHaveAttribute('href', '/watchlist'))
  })
})
