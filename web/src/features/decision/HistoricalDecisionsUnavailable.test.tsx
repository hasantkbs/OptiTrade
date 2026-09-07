import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HistoricalDecisionsUnavailable } from './HistoricalDecisionsUnavailable'

describe('HistoricalDecisionsUnavailable', () => {
  it('honestly reports the missing backend capability instead of fabricating a decision history table', () => {
    render(<HistoricalDecisionsUnavailable />)
    expect(screen.getByText('Historical decision tracking is not currently exposed by the backend')).toBeInTheDocument()
    expect(screen.getByText(/no API endpoint returns that history yet/)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})
