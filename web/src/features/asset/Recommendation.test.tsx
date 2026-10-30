import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Recommendation } from './Recommendation'
import type { PipelineResponse } from '../../api/types'

const response: PipelineResponse = {
  symbol: 'AAPL', decision: 'BUY', confidence: 0.72, expected_return: 0.034, expected_volatility: 0.18,
  engine_breakdown: [], evidence: ['Aggregate confidence above threshold'],
  risk: { risk_level: 'MEDIUM', expected_volatility: 0.18, data_sufficiency: 0.9 },
  explanation: 'Technical momentum outweighs neutral fundamentals.',
  metadata: { pipeline_version: '1.0.0', total_duration_ms: 120, stage_durations_ms: {}, engines_available: 3, engines_succeeded: 2, degraded: true, timestamp: '2026-01-01T20:00:00Z' },
}

describe('Recommendation', () => {
  it('prompts the user to run the analysis when nothing has happened yet', () => {
    render(<Recommendation isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Analyze' })).toBeInTheDocument()
  })

  it('renders the real decision and the plain-language explanation, with no engine jargon', () => {
    render(<Recommendation data={response} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByText('BUY')).toBeInTheDocument()
    expect(screen.getByText('Technical momentum outweighs neutral fundamentals.')).toBeInTheDocument()
    expect(screen.queryByText(/engines succeeded/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Expected return/)).not.toBeInTheDocument()
  })

  it('maps confidence 0.72 to "Yüksek güven"', () => {
    render(<Recommendation data={{ ...response, confidence: 0.72 }} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByText('Yüksek güven')).toBeInTheDocument()
  })

  it('maps confidence exactly 0.66 to "Yüksek güven" (boundary, inclusive)', () => {
    render(<Recommendation data={{ ...response, confidence: 0.66 }} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByText('Yüksek güven')).toBeInTheDocument()
  })

  it('maps confidence 0.65 to "Orta güven" (just below the high boundary)', () => {
    render(<Recommendation data={{ ...response, confidence: 0.65 }} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByText('Orta güven')).toBeInTheDocument()
  })

  it('maps confidence exactly 0.33 to "Orta güven" (boundary, inclusive)', () => {
    render(<Recommendation data={{ ...response, confidence: 0.33 }} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByText('Orta güven')).toBeInTheDocument()
  })

  it('maps confidence 0.32 to "Düşük güven" (just below the mid boundary)', () => {
    render(<Recommendation data={{ ...response, confidence: 0.32 }} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByText('Düşük güven')).toBeInTheDocument()
  })

  it('shows a HOLD decision with neutral treatment', () => {
    render(<Recommendation data={{ ...response, decision: 'HOLD' }} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.getByText('HOLD')).toBeInTheDocument()
  })
})

describe('Recommendation - chart AI conflict', () => {
  it('shows the warning line when decision is BUY and chart AI says SELL', () => {
    // Main response confidence (0.72, "Yüksek güven") deliberately
    // differs from chart_ai.confidence (0.4, "Orta güven") so this test
    // actually pins which confidence the warning line's word comes from
    // - with a shared 0.72 on both, a bug that read data.confidence
    // instead of data.chart_ai.confidence would pass unnoticed.
    render(
      <Recommendation
        data={{ ...response, decision: 'BUY', confidence: 0.72, chart_ai: { signal: 'SELL', confidence: 0.4 } }}
        isPending={false} isError={false} onAnalyze={vi.fn()}
      />,
    )
    expect(screen.getByText('SELL')).toBeInTheDocument()
    expect(screen.getByText(/disagrees · Orta güven/)).toBeInTheDocument()
    expect(screen.getByText('Yüksek güven')).toBeInTheDocument()
  })

  it('shows nothing extra when decision and chart AI agree', () => {
    render(
      <Recommendation
        data={{ ...response, decision: 'BUY', chart_ai: { signal: 'BUY', confidence: 0.72 } }}
        isPending={false} isError={false} onAnalyze={vi.fn()}
      />,
    )
    expect(screen.queryByText(/disagrees/i)).not.toBeInTheDocument()
  })

  it('shows nothing extra when chart AI is NEUTRAL', () => {
    render(
      <Recommendation
        data={{ ...response, decision: 'BUY', chart_ai: { signal: 'NEUTRAL', confidence: 0.5 } }}
        isPending={false} isError={false} onAnalyze={vi.fn()}
      />,
    )
    expect(screen.queryByText(/disagrees/i)).not.toBeInTheDocument()
  })

  it('shows nothing extra when decision is HOLD, even if chart AI has a strong opposite opinion', () => {
    render(
      <Recommendation
        data={{ ...response, decision: 'HOLD', chart_ai: { signal: 'SELL', confidence: 0.9 } }}
        isPending={false} isError={false} onAnalyze={vi.fn()}
      />,
    )
    expect(screen.queryByText(/disagrees/i)).not.toBeInTheDocument()
  })

  it('renders exactly as before when chart_ai is absent (today\'s shape for any symbol with no live model)', () => {
    render(<Recommendation data={response} isPending={false} isError={false} onAnalyze={vi.fn()} />)
    expect(screen.queryByText(/disagrees/i)).not.toBeInTheDocument()
  })
})
