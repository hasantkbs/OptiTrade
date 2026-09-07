import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Card } from '../components/ui/Card'
import { apiErrorMessage } from '../api/client'
import { useQuantAnalyze } from '../features/asset/hooks'
import { QuantDecision } from '../features/asset/QuantDecision'
import { EngineBreakdown } from '../features/asset/EngineBreakdown'
import { RiskPanel } from '../features/asset/RiskPanel'
import { ExplanationPanel } from '../features/asset/ExplanationPanel'
import { DecisionHeader } from '../features/decision/DecisionHeader'
import { SymbolPicker } from '../features/decision/SymbolPicker'
import { SystemEngineStatus } from '../features/decision/SystemEngineStatus'
import { HistoricalDecisionsUnavailable } from '../features/decision/HistoricalDecisionsUnavailable'
import styles from './DecisionsPage.module.css'

/**
 * /decisions - Decision Intelligence. Reuses WEB STEP 4's exact
 * `useQuantAnalyze` mutation and `QuantDecision`/`EngineBreakdown`/
 * `RiskPanel`/`ExplanationPanel` components (features/asset/*) rather
 * than a second, parallel decision-rendering implementation - the same
 * POST /quant/analyze response drives both this page and the Asset
 * Explorer (WEB STEP 5 §3). Only one symbol is ever analyzed at a time,
 * on explicit user action.
 */
export function DecisionsPage() {
  const queryClient = useQueryClient()
  const [symbol, setSymbol] = useState<string | null>(null)
  const quant = useQuantAnalyze(symbol ?? '')

  // Mirrors AssetDetailPage's auto-run-once-per-symbol guard: picking a
  // symbol runs it exactly once, never on every render: re-running the
  // SAME symbol again is only ever done via QuantDecision's own
  // explicit "Refresh analysis" button.
  const autoRunSymbol = useRef<string | null>(null)
  useEffect(() => {
    if (symbol && autoRunSymbol.current !== symbol) {
      autoRunSymbol.current = symbol
      quant.mutate()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol])

  // The result for whatever symbol is currently selected only - never
  // shows a previous symbol's decision while a new one is in flight.
  const currentResult = quant.data?.symbol === symbol ? quant.data : undefined

  function handleRefreshSystem() {
    void queryClient.invalidateQueries({ queryKey: ['dashboard', 'engines'] })
    void queryClient.invalidateQueries({ queryKey: ['watchlists'] })
  }

  return (
    <div className={styles.page}>
      <DecisionHeader onRefresh={handleRefreshSystem} isRefreshing={false} />

      <SymbolPicker activeSymbol={symbol} isAnalyzing={quant.isPending} onAnalyze={setSymbol} />

      {symbol ? (
        <div className={styles.analysisSection}>
          <div className={styles.analysisHeader}>
            <h2 className={styles.analysisTitle}>Analysis for {symbol}</h2>
            <Link to={`/assets/${symbol}`} className={styles.assetLink}>
              View full asset page →
            </Link>
          </div>

          <div className={styles.grid}>
            <div className={styles.mainColumn}>
              <QuantDecision
                data={currentResult}
                isPending={quant.isPending}
                isError={quant.isError}
                errorMessage={quant.isError ? apiErrorMessage(quant.error) : undefined}
                onAnalyze={() => quant.mutate()}
              />
              <EngineBreakdown engines={currentResult?.engine_breakdown ?? []} />
            </div>

            <div className={styles.sideColumn}>
              {currentResult ? (
                <RiskPanel risk={currentResult.risk} />
              ) : (
                <Card>
                  <p className={styles.placeholder}>Risk assessment will appear here once this symbol has been analyzed.</p>
                </Card>
              )}
              {currentResult?.explanation ? <ExplanationPanel explanation={currentResult.explanation} /> : null}
            </div>
          </div>
        </div>
      ) : (
        <Card>
          <p className={styles.placeholder}>
            Pick a symbol above to see its current decision, confidence, engine breakdown, evidence and risk.
          </p>
        </Card>
      )}

      <SystemEngineStatus />

      <HistoricalDecisionsUnavailable />
    </div>
  )
}
