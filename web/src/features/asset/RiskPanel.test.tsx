import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RiskPanel } from './RiskPanel'
import type { QuantRiskAssessment } from '../../api/types'

const risk: QuantRiskAssessment = { risk_level: 'MEDIUM', expected_volatility: 0.18, data_sufficiency: 0.9 }

describe('RiskPanel', () => {
  it('renders only the real fields the quant endpoint returns - never a fabricated stop-loss/take-profit/ATR', () => {
    render(<RiskPanel risk={risk} />)
    expect(screen.getByText('MEDIUM')).toBeInTheDocument()
    expect(screen.getByText('18.00%')).toBeInTheDocument()
    expect(screen.getByText('0.90')).toBeInTheDocument()
    expect(screen.queryByText(/stop.loss|take.profit|entry price|ATR/i)).not.toBeInTheDocument()
  })
})
