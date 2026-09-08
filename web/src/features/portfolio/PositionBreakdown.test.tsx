import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { PositionBreakdown } from './PositionBreakdown'
import type { PositionAnalytics } from '../../api/types'

const positions: PositionAnalytics[] = [
  {
    symbol: 'AAPL',
    quantity: 10,
    average_cost: 150,
    current_price: 180,
    cost_basis: 1500,
    current_value: 1800,
    unrealized_pnl: 300,
    unrealized_pnl_pct: 20,
    realized_pnl: 0,
    weight_pct: 30,
    sector: 'Technology',
    country: 'US',
    currency: 'USD',
  },
  {
    symbol: 'MSFT',
    quantity: 5,
    average_cost: 300,
    current_price: 280,
    cost_basis: 1500,
    current_value: 1400,
    unrealized_pnl: -100,
    unrealized_pnl_pct: -6.7,
    realized_pnl: 0,
    weight_pct: 45,
    sector: 'Technology',
    country: 'US',
    currency: 'USD',
  },
]

function renderTable(data = positions) {
  return render(
    <MemoryRouter>
      <PositionBreakdown positions={data} currency="USD" />
    </MemoryRouter>,
  )
}

describe('PositionBreakdown', () => {
  it('shows an honest empty state with no positions', () => {
    renderTable([])
    expect(screen.getByText('No open positions')).toBeInTheDocument()
  })

  it('sorts by weight descending by default (MSFT before AAPL)', () => {
    renderTable()
    const rows = screen.getAllByRole('row').slice(1)
    expect(within(rows[0]).getByText('MSFT')).toBeInTheDocument()
    expect(within(rows[1]).getByText('AAPL')).toBeInTheDocument()
  })

  it('re-sorts when a sortable header is clicked, using only real position fields', async () => {
    const user = userEvent.setup()
    renderTable()
    await user.click(screen.getByRole('columnheader', { name: /Symbol/ }))
    const rows = screen.getAllByRole('row').slice(1)
    expect(within(rows[0]).getByText('AAPL')).toBeInTheDocument()
  })

  it('links each position sector to the real Assets page', () => {
    renderTable()
    const links = screen.getAllByRole('link', { name: 'Technology' })
    expect(links[0]).toHaveAttribute('href', '/assets')
  })

  it('shows average cost and current price - real PositionAnalytics fields, never re-derived', () => {
    renderTable()
    const rows = screen.getAllByRole('row').slice(1)
    // Default sort is weight descending, so MSFT (weight 45) is first.
    expect(within(rows[0]).getByText('$300.00')).toBeInTheDocument()
    expect(within(rows[0]).getByText('$280.00')).toBeInTheDocument()
    expect(within(rows[1]).getByText('$150.00')).toBeInTheDocument()
    expect(within(rows[1]).getByText('$180.00')).toBeInTheDocument()
  })
})
