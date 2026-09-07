import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ExplanationPanel } from './ExplanationPanel'

describe('ExplanationPanel', () => {
  it('displays the real backend explanation and clearly separates it from the decision', () => {
    render(<ExplanationPanel explanation="Technical momentum outweighs neutral fundamentals." />)
    expect(screen.getByText('Technical momentum outweighs neutral fundamentals.')).toBeInTheDocument()
    expect(screen.getByText(/does not itself determine or adjust that decision/)).toBeInTheDocument()
  })
})
