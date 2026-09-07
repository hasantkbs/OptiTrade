import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PerformanceHistory } from './PerformanceHistory'

describe('PerformanceHistory', () => {
  it('shows real current P&L scalars and an honest unavailable state for history, never a fabricated chart', () => {
    render(<PerformanceHistory realizedPnl={500} unrealizedPnl={-200} sharpeRatio={1.24} currency="USD" />)
    expect(screen.getByText('$500')).toBeInTheDocument()
    expect(screen.getByText('-$200')).toBeInTheDocument()
    expect(screen.getByText('1.24')).toBeInTheDocument()
    expect(screen.getByText('Historical performance not available')).toBeInTheDocument()
  })

  it('shows an honest placeholder when the Sharpe ratio has not been computed yet', () => {
    render(<PerformanceHistory realizedPnl={0} unrealizedPnl={0} sharpeRatio={null} currency="USD" />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
