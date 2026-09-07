import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SymbolPicker } from './SymbolPicker'
import { watchlistApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  watchlistApi: { list: vi.fn(), items: vi.fn() },
}))

const mockedWatchlistApi = vi.mocked(watchlistApi)

function renderPicker(props: Partial<Parameters<typeof SymbolPicker>[0]> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const onAnalyze = vi.fn()
  render(
    <QueryClientProvider client={client}>
      <SymbolPicker activeSymbol={null} isAnalyzing={false} onAnalyze={onAnalyze} {...props} />
    </QueryClientProvider>,
  )
  return { onAnalyze }
}

const watchlist = { id: 1, owner: 'user-1', name: 'Core', created_at: '2026-01-01T00:00:00Z' }
const items = [
  { id: 1, watchlist_id: 1, symbol: 'AAPL', is_favorite: false, folder: null, tags: [], notes: '', added_at: '2026-01-01T00:00:00Z' },
  { id: 2, watchlist_id: 1, symbol: 'MSFT', is_favorite: false, folder: null, tags: [], notes: '', added_at: '2026-01-01T00:00:00Z' },
]

beforeEach(() => {
  vi.clearAllMocks()
  mockedWatchlistApi.list.mockResolvedValue([watchlist])
  mockedWatchlistApi.items.mockResolvedValue(items)
})

describe('SymbolPicker', () => {
  it('submits the typed symbol, uppercased and trimmed', async () => {
    const user = userEvent.setup()
    const { onAnalyze } = renderPicker()
    await user.type(screen.getByLabelText('Symbol'), 'aapl')
    await user.click(screen.getByRole('button', { name: 'Analyze' }))
    expect(onAnalyze).toHaveBeenCalledWith('AAPL')
  })

  it('does not submit an empty symbol', async () => {
    const user = userEvent.setup()
    const { onAnalyze } = renderPicker()
    expect(screen.getByRole('button', { name: 'Analyze' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Analyze' }))
    expect(onAnalyze).not.toHaveBeenCalled()
  })

  it('disables the input and button while an analysis is already running', () => {
    renderPicker({ isAnalyzing: true })
    expect(screen.getByLabelText('Symbol')).toBeDisabled()
    const button = screen.getByRole('button')
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
  })

  it('offers real watchlist symbols as quick-pick chips and analyzes on click', async () => {
    const user = userEvent.setup()
    const { onAnalyze } = renderPicker()
    expect(await screen.findByRole('button', { name: 'AAPL' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'MSFT' }))
    expect(onAnalyze).toHaveBeenCalledWith('MSFT')
  })

  it('disables watchlist chips while an analysis is in flight, never allowing a parallel scan', async () => {
    renderPicker({ isAnalyzing: true })
    expect(await screen.findByRole('button', { name: 'AAPL' })).toBeDisabled()
  })
})
