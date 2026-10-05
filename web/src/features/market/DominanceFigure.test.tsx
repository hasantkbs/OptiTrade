import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DominanceFigure } from './DominanceFigure'

describe('DominanceFigure', () => {
  it('renders the real percentage when available', () => {
    render(<DominanceFigure value={54.3} isLoading={false} />)
    expect(screen.getByText('54.3%')).toBeInTheDocument()
  })

  it('shows "unavailable" rather than a fabricated number when value is null', () => {
    render(<DominanceFigure value={null} isLoading={false} />)
    expect(screen.getByText('unavailable')).toBeInTheDocument()
  })

  it('shows a loading state', () => {
    render(<DominanceFigure value={null} isLoading />)
    expect(screen.queryByText('unavailable')).not.toBeInTheDocument()
  })
})
