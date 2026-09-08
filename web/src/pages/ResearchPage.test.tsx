import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ResearchPage } from './ResearchPage'

describe('ResearchPage', () => {
  it('honestly reports that Research Lab has no public API, per capability, instead of fabricating experiments/backtests', () => {
    render(<ResearchPage />)
    expect(screen.getByRole('heading', { name: 'Research Lab' })).toBeInTheDocument()
    expect(screen.getByText('Experiments')).toBeInTheDocument()
    expect(screen.getByText('Backtests')).toBeInTheDocument()
    expect(screen.getByText('Model analysis')).toBeInTheDocument()
    expect(screen.getByText(/fully isolated, offline research environment/)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('makes production vs. research isolation explicit', () => {
    render(<ResearchPage />)
    expect(screen.getByText('Production vs. research')).toBeInTheDocument()
    expect(screen.getByText(/never an automatic change to a production engine or weight/)).toBeInTheDocument()
  })
})
