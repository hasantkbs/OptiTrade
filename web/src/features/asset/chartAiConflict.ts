import type { ChartAISignal, Prediction } from '../../api/types'

/** A conflict is strictly BUY-vs-SELL in either direction - NEUTRAL
 * chart-AI signals and HOLD decisions never count, by design (see
 * docs/superpowers/specs/2026-10-30-chart-ai-conflict-indicator-design.md's
 * "Conflict definition" - this is deliberately the rarer, stricter
 * reading so the indicator stays meaningful rather than showing on
 * roughly half of all live symbols). */
export function isConflict(decision: Prediction, chartAiSignal: ChartAISignal['signal']): boolean {
  return (
    (decision === 'BUY' && chartAiSignal === 'SELL') ||
    (decision === 'SELL' && chartAiSignal === 'BUY')
  )
}
