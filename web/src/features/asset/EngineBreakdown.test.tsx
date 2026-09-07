import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EngineBreakdown } from './EngineBreakdown'
import type { EngineBreakdownItem } from '../../api/types'

const engines: EngineBreakdownItem[] = [
  {
    engine_name: 'TechnicalEngine',
    engine_version: '1.0.0',
    status: 'success',
    prediction: 'BUY',
    confidence: 0.8,
    expected_return: 0.04,
    volatility: 0.15,
    evidence: ['RSI oversold reversal'],
  },
  {
    engine_name: 'FundamentalEngine',
    engine_version: '1.0.0',
    status: 'success',
    prediction: 'HOLD',
    confidence: 0.5,
    expected_return: 0.01,
    volatility: 0.1,
    evidence: [],
  },
  {
    engine_name: 'NewsEngine',
    engine_version: '1.0.0',
    status: 'failed',
    prediction: null,
    confidence: null,
    expected_return: null,
    volatility: null,
    evidence: [],
  },
]

describe('EngineBreakdown', () => {
  it('shows an honest empty state before any analysis has run', () => {
    render(<EngineBreakdown engines={[]} />)
    expect(screen.getByText('No engine data yet')).toBeInTheDocument()
  })

  it('renders one card per real engine, splitting the fixed name from the version', () => {
    render(<EngineBreakdown engines={engines} />)
    expect(screen.getByText('Technical')).toBeInTheDocument()
    expect(screen.getByText('Fundamental')).toBeInTheDocument()
    expect(screen.getByText('News')).toBeInTheDocument()
    expect(screen.getByText('RSI oversold reversal')).toBeInTheDocument()
  })

  it('shows a failed engine honestly, without inventing a vote or confidence for it', () => {
    render(<EngineBreakdown engines={engines} />)
    expect(screen.getByText('failed')).toBeInTheDocument()
  })

  it('never labels the aggregate evidence text as if it were a numeric score', () => {
    render(<EngineBreakdown engines={engines} />)
    expect(screen.getByText('No supporting evidence returned.')).toBeInTheDocument()
  })
})
