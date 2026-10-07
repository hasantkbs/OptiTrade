import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AddSymbolDialog } from './AddSymbolDialog'
import { marketApi, watchlistApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  marketApi: { watchlist: vi.fn() },
  watchlistApi: { addItem: vi.fn() },
}))

const mockedMarketApi = vi.mocked(marketApi)
const mockedWatchlistApi = vi.mocked(watchlistApi)

const info = {
  name: 'x', flag: 'x', currency: 'x', timezone: 'x', session_open: 'x', session_close: 'x',
  index_symbol: 'x', index_name: 'x', description: 'x',
}

function renderDialog(open = true, onClose = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    onClose,
    ...render(
      <QueryClientProvider client={client}>
        <AddSymbolDialog open={open} watchlistId={7} onClose={onClose} />
      </QueryClientProvider>,
    ),
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedMarketApi.watchlist.mockImplementation((market: string) =>
    Promise.resolve({
      market,
      info,
      watchlist: [],
      symbols: (market === 'US' ? { AAPL: 'Apple' } : {}) as Record<string, string>,
    }),
  )
})

describe('AddSymbolDialog', () => {
  it('renders nothing when closed', () => {
    renderDialog(false)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('adds the picked symbol via POST /watchlists/{id}/items and closes on success', async () => {
    const user = userEvent.setup()
    mockedWatchlistApi.addItem.mockResolvedValueOnce({
      id: 1, watchlist_id: 7, symbol: 'AAPL', is_favorite: false, folder: null, tags: [], notes: '',
      added_at: '2026-01-01T00:00:00Z',
    })
    const { onClose } = renderDialog()

    await user.type(screen.getByLabelText('Search stocks or crypto'), 'AAPL')
    await user.click(await screen.findByRole('button', { name: /AAPL/ }))

    await waitFor(() => expect(mockedWatchlistApi.addItem).toHaveBeenCalledWith(7, { symbol: 'AAPL' }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('closes without adding when Close is clicked', async () => {
    const user = userEvent.setup()
    const { onClose } = renderDialog()
    await user.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalled()
    expect(mockedWatchlistApi.addItem).not.toHaveBeenCalled()
  })
})
