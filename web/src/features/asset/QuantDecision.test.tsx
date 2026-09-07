import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { QuantDecision } from './QuantDecision'
import type { PipelineResponse } from '../../api/types'

const response: PipelineResponse = {
  symbol: 'AAPL',
  decision: 'BUY',
  confidence: 0.72,
  expected_return: 0.034,
  expected_volatility: 0.18,
  engine_breakdown: [],
  evidence: ['Aggregate confidence above threshold'],
  risk: { risk_level: 'MEDIUM', expected_volatility: 0.18, data_sufficiency: 0.9 },
  explanation: 'Technical momentum outweighs neutral fundamentals.',
  metadata: {
    pipeline_version: '1.0.0',
    total_duration_ms: 120,
    stage_durations_ms: {},
    engines_available: 3,
    engines_succeeded: 2,
    degraded: true,
    timestamp: '2026-01-01T20:00:00Z',
  },
}

describe('QuantDecision', () => {
  it('prompts the user to run the analysis when nothing has happened yet', () => {
    render(<QuantDecision isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByText('Run the Decision Engine to see a quant decision for this symbol.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Analyze' })).toBeInTheDocument()
  })

  it('disables the analyze button while an analysis is already in flight', () => {
    const onAnalyze = vi.fn()
    render(<QuantDecision isPending isError={false} onAnalyze={onAnalyze} />)
    const button = screen.getByRole('button')
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
  })

  it('shows a retryable error when the analysis fails with no prior result', () => {
    render(<QuantDecision isPending={false} isError errorMessage="pipeline error" onAnalyze={vi.fn()} />)
    expect(screen.getByText('pipeline error')).toBeInTheDocument()
  })

  it('renders the real backend decision, never recalculating it, and separates confidence from expected return', () => {
    render(<QuantDecision data={response} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByText('BUY')).toBeInTheDocument()
    expect(screen.getByText('72%')).toBeInTheDocument()
    expect(screen.getByText('+3.40%')).toBeInTheDocument()
    expect(screen.getByText('18.00%')).toBeInTheDocument()
    expect(screen.getByText('2/3 engines succeeded')).toBeInTheDocument()
    expect(screen.getByText('Degraded run')).toBeInTheDocument()
    expect(screen.getByText('Aggregate confidence above threshold')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh analysis' })).toBeInTheDocument()
  })

  it('shows a HOLD decision with neutral treatment, not an invented color scheme', () => {
    render(<QuantDecision data={{ ...response, decision: 'HOLD' }} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByText('HOLD')).toBeInTheDocument()
  })

  it('keeps showing the previous result with a stale note when a refresh fails', () => {
    render(<QuantDecision data={response} isPending={false} isError errorMessage="timeout" onAnalyze={vi.fn()} />)
    expect(screen.getByText('BUY')).toBeInTheDocument()
    expect(screen.getByText('The last refresh failed - showing the previous result above.')).toBeInTheDocument()
  })
})
