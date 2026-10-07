import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SymbolSearch } from './SymbolSearch'
import { marketApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  marketApi: { watchlist: vi.fn() },
}))

const mockedMarketApi = vi.mocked(marketApi)

const info = {
  name: 'x', flag: 'x', currency: 'x', timezone: 'x', session_open: 'x', session_close: 'x',
  index_symbol: 'x', index_name: 'x', description: 'x',
}

function renderSearch(onSelect = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    onSelect,
    ...render(
      <QueryClientProvider client={client}>
        <SymbolSearch onSelect={onSelect} />
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
      symbols: (
        market === 'TR' ? { 'GARAN.IS': 'Garanti BBVA' } : market === 'US' ? { AAPL: 'Apple' } : { 'BTC-USD': 'Bitcoin' }
      ) as Record<string, string>,
    }),
  )
})

describe('SymbolSearch', () => {
  it('shows no results before typing anything', () => {
    renderSearch()
    expect(screen.queryByRole('button', { name: /AAPL/ })).not.toBeInTheDocument()
  })

  it('matches by symbol and calls onSelect with the canonical, correctly-suffixed symbol', async () => {
    const user = userEvent.setup()
    const { onSelect } = renderSearch()

    await user.type(screen.getByLabelText('Search stocks or crypto'), 'GARAN')
    await user.click(await screen.findByRole('button', { name: /GARAN.IS/ }))

    expect(onSelect).toHaveBeenCalledWith('GARAN.IS')
  })

  it('matches by company name, not only by ticker', async () => {
    const user = userEvent.setup()
    renderSearch()

    await user.type(screen.getByLabelText('Search stocks or crypto'), 'bitcoin')
    expect(await screen.findByRole('button', { name: /BTC-USD/ })).toBeInTheDocument()
  })

  it('shows an honest empty state for a query that matches nothing', async () => {
    const user = userEvent.setup()
    renderSearch()

    await user.type(screen.getByLabelText('Search stocks or crypto'), 'zzzznotreal')
    expect(await screen.findByText('No matching symbol.')).toBeInTheDocument()
  })
})
