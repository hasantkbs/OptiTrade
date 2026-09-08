import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { WatchlistPage } from './WatchlistPage'
import { watchlistApi } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  watchlistApi: { list: vi.fn(), items: vi.fn(), create: vi.fn() },
}))

const mockedWatchlistApi = vi.mocked(watchlistApi)

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/watchlist']}>
        <WatchlistPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const watchlistA = { id: 1, owner: 'user-1', name: 'Core Holdings', created_at: '2026-01-01T00:00:00Z' }

beforeEach(() => {
  vi.clearAllMocks()
})

describe('WatchlistPage', () => {
  it('shows an honest empty state with a Create watchlist action when the user has none', async () => {
    mockedWatchlistApi.list.mockResolvedValueOnce([])
    renderPage()
    await waitFor(() => expect(screen.getByText('No watchlists yet')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Create watchlist' })).toBeInTheDocument()
  })

  it('shows a retryable error state when the watchlist list fails to load', async () => {
    mockedWatchlistApi.list.mockRejectedValueOnce(new Error('network down'))
    renderPage()
    await waitFor(() => expect(screen.getByText("Couldn't load this data")).toBeInTheDocument())
  })

  it('opens the create dialog from the empty state, and validates a blank name without calling the API', async () => {
    const user = userEvent.setup()
    mockedWatchlistApi.list.mockResolvedValueOnce([])
    renderPage()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Create watchlist' })).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'Create watchlist' }))
    const dialog = screen.getByRole('dialog')

    await user.click(within(dialog).getByRole('button', { name: 'Create watchlist' }))
    expect(await screen.findByText('Watchlist name is required.')).toBeInTheDocument()
    expect(mockedWatchlistApi.create).not.toHaveBeenCalled()
  })

  it('creates a watchlist from the empty state and shows it without a manual refresh', async () => {
    const user = userEvent.setup()
    // Stateful mock, not a fixed once-queue - see the matching comment
    // in PortfolioPage.test.tsx's equivalent test.
    let watchlists: typeof watchlistA[] = []
    mockedWatchlistApi.list.mockImplementation(() => Promise.resolve(watchlists))
    mockedWatchlistApi.create.mockImplementationOnce(async () => {
      watchlists = [watchlistA]
      return watchlistA
    })
    mockedWatchlistApi.items.mockResolvedValue([])
    renderPage()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Create watchlist' })).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'Create watchlist' }))
    const dialog = screen.getByRole('dialog')
    await user.type(within(dialog).getByLabelText('Watchlist name'), 'Core Holdings')
    await user.click(within(dialog).getByRole('button', { name: 'Create watchlist' }))

    await waitFor(() => expect(mockedWatchlistApi.create).toHaveBeenCalledWith({ name: 'Core Holdings' }))
    await waitFor(() => expect(screen.getByText('Core Holdings')).toBeInTheDocument())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows the API error and keeps the dialog open when creation fails', async () => {
    const user = userEvent.setup()
    mockedWatchlistApi.list.mockResolvedValueOnce([])
    mockedWatchlistApi.create.mockRejectedValueOnce({
      isAxiosError: true,
      response: { data: { detail: 'name must not be blank' } },
    })
    renderPage()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Create watchlist' })).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'Create watchlist' }))
    const dialog = screen.getByRole('dialog')
    await user.type(within(dialog).getByLabelText('Watchlist name'), 'x')
    await user.click(within(dialog).getByRole('button', { name: 'Create watchlist' }))

    expect(await screen.findByText('name must not be blank')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('closes the dialog on Cancel without calling the API', async () => {
    const user = userEvent.setup()
    mockedWatchlistApi.list.mockResolvedValueOnce([])
    renderPage()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Create watchlist' })).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'Create watchlist' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(mockedWatchlistApi.create).not.toHaveBeenCalled()
  })

  it('renders tracked symbols for an existing watchlist', async () => {
    mockedWatchlistApi.list.mockResolvedValue([watchlistA])
    mockedWatchlistApi.items.mockResolvedValue([
      { id: 1, watchlist_id: 1, symbol: 'AAPL', is_favorite: true, folder: null, tags: [], notes: '', added_at: '2026-01-01T00:00:00Z' },
    ])
    renderPage()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Core Holdings' })).toBeInTheDocument())
    expect(await screen.findByRole('link', { name: 'AAPL' })).toBeInTheDocument()
  })

  /**
   * Multi-resource UX audit finding: there is no watchlist selector
   * anywhere in the app (every consumer independently reads
   * `watchlists[0]`), so a second watchlist created via a "New
   * watchlist" action here would be permanently unreachable - a genuine
   * dead end, not a supported feature. This must stay off until a real
   * selector exists.
   */
  it('does not offer a way to create another watchlist once one already exists', async () => {
    mockedWatchlistApi.list.mockResolvedValue([watchlistA])
    mockedWatchlistApi.items.mockResolvedValue([])
    renderPage()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Core Holdings' })).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'New watchlist' })).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('points an empty existing watchlist to the Assets page rather than a dead end', async () => {
    mockedWatchlistApi.list.mockResolvedValueOnce([watchlistA])
    mockedWatchlistApi.items.mockResolvedValueOnce([])
    renderPage()
    await waitFor(() => expect(screen.getByText('No symbols yet')).toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'Browse assets' })).toHaveAttribute('href', '/assets')
  })
})
