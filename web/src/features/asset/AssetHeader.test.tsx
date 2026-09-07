import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AssetHeader } from './AssetHeader'
import type { PriceQuote } from '../../api/types'

const price: PriceQuote = { symbol: 'AAPL', price: 189.5, change_pct: 1.25, timestamp: '2026-01-01T20:00:00Z' }

function baseWatchlist() {
  return { hasWatchlist: true, isInWatchlist: false, isLoading: false, isMutating: false, add: vi.fn(), remove: vi.fn() }
}

function renderHeader(props: Partial<Parameters<typeof AssetHeader>[0]> = {}) {
  const onRetry = vi.fn()
  const onRefresh = vi.fn()
  render(
    <MemoryRouter>
      <AssetHeader
        symbol="AAPL"
        isLoading={false}
        isError={false}
        onRetry={onRetry}
        onRefresh={onRefresh}
        isRefreshing={false}
        watchlist={baseWatchlist()}
        {...props}
      />
    </MemoryRouter>,
  )
  return { onRetry, onRefresh }
}

describe('AssetHeader', () => {
  it('shows a loading skeleton while price is loading', () => {
    renderHeader({ isLoading: true })
    expect(screen.getByText('AAPL')).toBeInTheDocument()
  })

  it('shows a retryable error when price fails to load', async () => {
    const user = userEvent.setup()
    const { onRetry } = renderHeader({ isError: true, errorMessage: 'network down' })
    expect(screen.getByText('network down')).toBeInTheDocument()
    await user.click(screen.getByText('Try again'))
    expect(onRetry).toHaveBeenCalled()
  })

  it('renders the real price and change_pct from the backend, never fabricated', () => {
    renderHeader({ price })
    expect(screen.getByText('189.5')).toBeInTheDocument()
    expect(screen.getByText('+1.25%')).toBeInTheDocument()
  })

  it('offers "Add to watchlist" when the symbol is not tracked, and calls add() on click', async () => {
    const user = userEvent.setup()
    const add = vi.fn()
    renderHeader({ price, watchlist: { ...baseWatchlist(), add } })
    await user.click(screen.getByRole('button', { name: 'Add to watchlist' }))
    expect(add).toHaveBeenCalled()
  })

  it('offers "Remove from watchlist" when the symbol is already tracked', () => {
    renderHeader({ price, watchlist: { ...baseWatchlist(), isInWatchlist: true } })
    expect(screen.getByRole('button', { name: 'Remove from watchlist' })).toBeInTheDocument()
  })

  it('shows an honest hint instead of a watchlist action when no watchlist exists', () => {
    renderHeader({ price, watchlist: { ...baseWatchlist(), hasWatchlist: false } })
    expect(screen.getByText('Create a watchlist to track this symbol')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /watchlist/i })).not.toBeInTheDocument()
  })

  it('calls onRefresh when Refresh is clicked', async () => {
    const user = userEvent.setup()
    const { onRefresh } = renderHeader({ price })
    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    expect(onRefresh).toHaveBeenCalled()
  })
})
