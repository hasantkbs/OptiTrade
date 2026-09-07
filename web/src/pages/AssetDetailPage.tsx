import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { EmptyState } from '../components/ui/EmptyState'
import { apiErrorMessage, isNotFoundError } from '../api/client'
import { useChart, usePrice, useQuantAnalyze, useAssetWatchlistState } from '../features/asset/hooks'
import { AssetHeader } from '../features/asset/AssetHeader'
import { PriceChart } from '../features/asset/PriceChart'
import { QuantDecision } from '../features/asset/QuantDecision'
import { EngineBreakdown } from '../features/asset/EngineBreakdown'
import { RiskPanel } from '../features/asset/RiskPanel'
import { ExplanationPanel } from '../features/asset/ExplanationPanel'
import type { ChartPeriod } from '../api/types'
import styles from './AssetDetailPage.module.css'

/**
 * /assets/:symbol - the canonical Asset Explorer route every symbol
 * link in the app (dashboard watchlist rows, portfolio positions, the
 * Watchlist page) points to (WEB STEP 4 §2, §12). `symbol` comes only
 * from the URL, never hardcoded. If GET /price/{symbol} 404s, the
 * backend has no market data for it at all (main.py::get_current_price
 * raises 404 when `fetch_history` returns empty) - treated as "unknown
 * symbol" for the whole page, since chart/quant would fail identically
 * for the same reason. Any other price failure (network/500) does not
 * block the rest of the page (WEB STEP 4 §16): chart and quant fetch
 * independently regardless.
 */
export function AssetDetailPage() {
  const { symbol = '' } = useParams<{ symbol: string }>()
  const normalizedSymbol = symbol.toUpperCase()
  const [period, setPeriod] = useState<ChartPeriod>('3mo')

  const price = usePrice(normalizedSymbol)
  const chart = useChart(normalizedSymbol, period)
  const quant = useQuantAnalyze(normalizedSymbol)
  const watchlist = useAssetWatchlistState(normalizedSymbol)

  // Waits for price to confirm the symbol is real before spending the
  // rate-limited (10/minute) /quant/analyze call on it - an invalid
  // symbol never reaches this, since price.isSuccess never becomes true.
  const autoRunSymbol = useRef<string | null>(null)
  useEffect(() => {
    if (price.isSuccess && autoRunSymbol.current !== normalizedSymbol) {
      autoRunSymbol.current = normalizedSymbol
      quant.mutate()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [normalizedSymbol, price.isSuccess])

  function refreshAll() {
    void price.refetch()
    void chart.refetch()
  }

  if (price.isError && isNotFoundError(price.error)) {
    return (
      <div className={styles.page}>
        <EmptyState
          variant="unavailable"
          title={`"${normalizedSymbol}" not found`}
          description="The backend has no market data for this symbol."
        />
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <AssetHeader
        symbol={normalizedSymbol}
        price={price.data}
        isLoading={price.isLoading}
        isError={price.isError}
        errorMessage={price.isError ? apiErrorMessage(price.error) : undefined}
        onRetry={() => void price.refetch()}
        onRefresh={refreshAll}
        isRefreshing={price.isFetching || chart.isFetching}
        watchlist={watchlist}
      />

      <div className={styles.grid}>
        <div className={styles.chart}>
          <PriceChart
            chart={chart.data}
            isLoading={chart.isLoading}
            isError={chart.isError}
            errorMessage={chart.isError ? apiErrorMessage(chart.error) : undefined}
            onRetry={() => void chart.refetch()}
            period={period}
            onPeriodChange={setPeriod}
          />
        </div>

        <div className={styles.decision}>
          <QuantDecision
            data={quant.data}
            isPending={quant.isPending}
            isError={quant.isError}
            errorMessage={quant.isError ? apiErrorMessage(quant.error) : undefined}
            onAnalyze={() => quant.mutate()}
          />
        </div>

        <div className={styles.engines}>
          <EngineBreakdown engines={quant.data?.engine_breakdown ?? []} />
        </div>

        <div className={styles.risk}>
          {quant.data ? (
            <RiskPanel risk={quant.data.risk} />
          ) : (
            <EmptyState title="Risk" description="Run the analysis to see this run's risk assessment." variant="unavailable" />
          )}
        </div>

        <div className={styles.explanation}>
          {quant.data?.explanation ? (
            <ExplanationPanel explanation={quant.data.explanation} />
          ) : null}
        </div>
      </div>
    </div>
  )
}
