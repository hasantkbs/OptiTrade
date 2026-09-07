import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Diversification } from './Diversification'

describe('Diversification', () => {
  it('shows an honest message when not yet computed', () => {
    render(<Diversification score={null} />)
    expect(screen.getByText('Not yet computed for this portfolio.')).toBeInTheDocument()
  })

  it('renders the real bounded score without an invented qualitative label', () => {
    render(<Diversification score={0.73} />)
    expect(screen.getByText('0.73')).toBeInTheDocument()
    expect(screen.queryByText(/good|poor|excellent/i)).not.toBeInTheDocument()
  })
})
