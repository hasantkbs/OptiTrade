import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CashExposure } from './CashExposure'
import type { AllocationBreakdown } from '../../api/types'

const allocation: AllocationBreakdown = {
  by_symbol_pct: { AAPL: 96 },
  by_sector_pct: { Technology: 96 },
  by_country_pct: {},
  by_currency_pct: {},
  cash_weight_pct: 4,
}

describe('CashExposure', () => {
  it('uses the real backend cash_weight_pct and its unambiguous complement, never recomputing the backend percentage itself', () => {
    render(<CashExposure allocation={allocation} cashBalance={1000} totalValue={25000} currency="USD" />)
    expect(screen.getByText('Invested 96.0%')).toBeInTheDocument()
    expect(screen.getByText('Cash 4.0%')).toBeInTheDocument()
    expect(screen.getByText('$1,000')).toBeInTheDocument()
    expect(screen.getByText('$24,000')).toBeInTheDocument()
  })
})
