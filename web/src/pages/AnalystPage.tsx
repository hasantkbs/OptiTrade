import { useEffect, useRef, useState } from 'react'
import { Card } from '../components/ui/Card'
import { apiErrorMessage } from '../api/client'
import { useQuantAnalyze } from '../features/asset/hooks'
import { QuantDecision } from '../features/asset/QuantDecision'
import { EngineBreakdown } from '../features/asset/EngineBreakdown'
import { RiskPanel } from '../features/asset/RiskPanel'
import { ExplanationPanel } from '../features/asset/ExplanationPanel'
import { SymbolPicker } from '../features/decision/SymbolPicker'
import styles from './AnalystPage.module.css'

/**
 * /ai-analyst - the existing WEB STEP 1 route/nav item, replacing its
 * "not available yet" stub. Reuses WEB STEP 4's exact `useQuantAnalyze`
 * mutation, `QuantDecision`/`EngineBreakdown`/`RiskPanel`/
 * `ExplanationPanel` components, and WEB STEP 5's `SymbolPicker` -
 * nothing here recomputes a decision, votes between engines, or calls
 * an LLM directly; `explanation` is POST /quant/analyze's own field,
 * displayed downstream of (never as the source of) the decision above
 * it. No chat, streaming, conversation history, or model SDK exists
 * here or anywhere in this app.
 */
export function AnalystPage() {
  const [symbol, setSymbol] = useState<string | null>(null)
  const quant = useQuantAnalyze(symbol ?? '')

  const autoRunSymbol = useRef<string | null>(null)
  useEffect(() => {
    if (symbol && autoRunSymbol.current !== symbol) {
      autoRunSymbol.current = symbol
      quant.mutate()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol])

  const currentResult = quant.data?.symbol === symbol ? quant.data : undefined

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>AI Analyst</h1>
        <p className={styles.subtitle}>
          A plain-language explanation of the quantitative Decision Engine's current output for one symbol. The
          explanation is generated downstream of the decision below - it describes the decision, it does not produce
          it.
        </p>
      </div>

      <SymbolPicker activeSymbol={symbol} isAnalyzing={quant.isPending} onAnalyze={setSymbol} />

      {symbol ? (
        <div className={styles.body}>
          <QuantDecision
            data={currentResult}
            isPending={quant.isPending}
            isError={quant.isError}
            errorMessage={quant.isError ? apiErrorMessage(quant.error) : undefined}
            onAnalyze={() => quant.mutate()}
          />

          {currentResult?.explanation ? <ExplanationPanel explanation={currentResult.explanation} /> : null}

          <div className={styles.twoUp}>
            <EngineBreakdown engines={currentResult?.engine_breakdown ?? []} />
            {currentResult ? (
              <RiskPanel risk={currentResult.risk} />
            ) : (
              <Card>
                <p className={styles.placeholder}>Risk context will appear here once this symbol has been analyzed.</p>
              </Card>
            )}
          </div>
        </div>
      ) : (
        <Card>
          <p className={styles.placeholder}>Pick a symbol above to see its current decision and AI-generated explanation.</p>
        </Card>
      )}
    </div>
  )
}
