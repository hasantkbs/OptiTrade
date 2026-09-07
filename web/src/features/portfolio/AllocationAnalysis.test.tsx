import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { AllocationAnalysis } from './AllocationAnalysis'
import type { AllocationBreakdown } from '../../api/types'

const allocation: AllocationBreakdown = {
  by_symbol_pct: { AAPL: 42, MSFT: 30, GOOG: 24 },
  by_sector_pct: { Technology: 96 },
  by_country_pct: {},
  by_currency_pct: {},
  cash_weight_pct: 4,
}

describe('AllocationAnalysis', () => {
  it('renders the symbol breakdown by default and calls out the largest holding', async () => {
    render(<AllocationAnalysis allocation={allocation} />)
    await waitFor(() => expect(screen.getByLabelText('Portfolio allocation by symbol')).toBeInTheDocument())
    expect(screen.getByText(/Largest allocation:/)).toBeInTheDocument()
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('42.0%')).toBeInTheDocument()
  })

  it('switches to the sector breakdown when the tab is clicked', async () => {
    const user = userEvent.setup()
    render(<AllocationAnalysis allocation={allocation} />)
    await waitFor(() => expect(screen.getByLabelText('Portfolio allocation by symbol')).toBeInTheDocument())
    await user.click(screen.getByRole('tab', { name: 'By sector' }))
    await waitFor(() => expect(screen.getByLabelText('Portfolio allocation by sector')).toBeInTheDocument())
  })

  it('shows an honest empty state when there is no allocation data', async () => {
    render(
      <AllocationAnalysis
        allocation={{ by_symbol_pct: {}, by_sector_pct: {}, by_country_pct: {}, by_currency_pct: {}, cash_weight_pct: 100 }}
      />,
    )
    await waitFor(() => expect(screen.getByText('No positions yet')).toBeInTheDocument())
  })

  it('renders without crashing in dark theme', async () => {
    document.documentElement.setAttribute('data-theme', 'dark')
    render(<AllocationAnalysis allocation={allocation} />)
    await waitFor(() => expect(screen.getByLabelText('Portfolio allocation by symbol')).toBeInTheDocument())
    document.documentElement.removeAttribute('data-theme')
  })
})
