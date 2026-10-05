import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { EmptyState } from '../components/ui/EmptyState'
import { apiErrorMessage, isNotFoundError } from '../api/client'
import { useChart, usePrice, useQuantAnalyze, useAssetWatchlistState, useAssetNews } from '../features/asset/hooks'
import { AssetHeader } from '../features/asset/AssetHeader'
import { PriceChart } from '../features/asset/PriceChart'
import { Recommendation } from '../features/asset/Recommendation'
import { AssetNews } from '../features/asset/AssetNews'
import type { ChartPeriod } from '../api/types'
import styles from './AssetDetailPage.module.css'

/**
 * /assets/:symbol - the canonical asset page every symbol link in the
 * app points to. `symbol` comes only from the URL, never hardcoded.
 * If GET /price/{symbol} 404s, the backend has no market data for it
 * at all - treated as "unknown symbol" for the whole page.
 */
export function AssetDetailPage() {
  const { symbol = '' } = useParams<{ symbol: string }>()
  const normalizedSymbol = symbol.toUpperCase()
  const [period, setPeriod] = useState<ChartPeriod>('3mo')

  const price = usePrice(normalizedSymbol)
  const chart = useChart(normalizedSymbol, period)
  const quant = useQuantAnalyze(normalizedSymbol)
  const watchlist = useAssetWatchlistState(normalizedSymbol)
  const news = useAssetNews(normalizedSymbol)

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

        <div className={styles.recommendation}>
          <Recommendation
            data={quant.data}
            isPending={quant.isPending}
            isError={quant.isError}
            errorMessage={quant.isError ? apiErrorMessage(quant.error) : undefined}
            onAnalyze={() => quant.mutate()}
          />
        </div>

        <div className={styles.news}>
          <AssetNews
            news={news.data}
            isLoading={news.isLoading}
            isError={news.isError}
            errorMessage={news.isError ? apiErrorMessage(news.error) : undefined}
          />
        </div>
      </div>
    </div>
  )
}
