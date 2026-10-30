import { describe, expect, it } from 'vitest'
import { isConflict } from './chartAiConflict'

describe('isConflict', () => {
  it('is a conflict when decision is BUY and chart AI says SELL', () => {
    expect(isConflict('BUY', 'SELL')).toBe(true)
  })

  it('is a conflict when decision is SELL and chart AI says BUY', () => {
    expect(isConflict('SELL', 'BUY')).toBe(true)
  })

  it('is NOT a conflict when both sides agree on BUY', () => {
    expect(isConflict('BUY', 'BUY')).toBe(false)
  })

  it('is NOT a conflict when both sides agree on SELL', () => {
    expect(isConflict('SELL', 'SELL')).toBe(false)
  })

  it('is NOT a conflict when chart AI is NEUTRAL, regardless of decision', () => {
    expect(isConflict('BUY', 'NEUTRAL')).toBe(false)
    expect(isConflict('SELL', 'NEUTRAL')).toBe(false)
    expect(isConflict('HOLD', 'NEUTRAL')).toBe(false)
  })

  it('is NOT a conflict when decision is HOLD, regardless of chart AI signal', () => {
    expect(isConflict('HOLD', 'BUY')).toBe(false)
    expect(isConflict('HOLD', 'SELL')).toBe(false)
  })
})
