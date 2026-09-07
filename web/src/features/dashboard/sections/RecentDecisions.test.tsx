import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RecentDecisions } from './RecentDecisions'

describe('RecentDecisions', () => {
  it('honestly reports the missing backend endpoint instead of fabricating data', () => {
    render(<RecentDecisions />)
    expect(screen.getByText('Not available yet')).toBeInTheDocument()
    expect(screen.getByText(/doesn't currently expose a decision execution feed/i)).toBeInTheDocument()
  })
})
