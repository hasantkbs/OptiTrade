import { useNavigate } from 'react-router-dom'
import { Button } from '../../components/ui/Button'
import { Skeleton } from '../../components/ui/Skeleton'
import { Tooltip } from '../../components/ui/Tooltip'
import type { PriceQuote } from '../../api/types'
import type { useAssetWatchlistState } from './hooks'
import styles from './AssetHeader.module.css'

interface AssetHeaderProps {
  symbol: string
  price?: PriceQuote
  isLoading: boolean
  isError: boolean
  errorMessage?: string
  onRetry: () => void
  onRefresh: () => void
  isRefreshing: boolean
  watchlist: ReturnType<typeof useAssetWatchlistState>
}

/**
 * Only real fields from GET /price/{symbol} (a plain dict:
 * symbol/price/change_pct/timestamp - main.py::get_current_price) are
 * shown. There is no company name, exchange, or currency anywhere in
 * the backend for a symbol, so none is displayed or guessed
 * (WEB STEP 4 §3, §24) - the price is a bare number with a tooltip
 * saying exactly that.
 */
export function AssetHeader({ symbol, price, isLoading, isError, errorMessage, onRetry, onRefresh, isRefreshing, watchlist }: AssetHeaderProps) {
  const navigate = useNavigate()

  return (
    <div className={styles.header}>
      <div>
        <button type="button" className={styles.backLink} onClick={() => navigate(-1)}>
          ← Back
        </button>
        <h1 className={styles.symbol}>{symbol}</h1>

        {isLoading ? (
          <Skeleton width="10rem" height="1.75rem" />
        ) : isError ? (
          <div className={styles.priceError}>
            <span>{errorMessage ?? "Couldn't load price"}</span>
            <button type="button" className={styles.retryLink} onClick={onRetry}>
              Try again
            </button>
          </div>
        ) : price ? (
          <div className={styles.priceRow}>
            <Tooltip content="The backend does not report a currency for this figure - shown exactly as returned.">
              <span className={`num ${styles.price}`}>{price.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
            </Tooltip>
            <span className={`num ${styles.change} ${price.change_pct >= 0 ? styles.positive : styles.negative}`}>
              {price.change_pct >= 0 ? '+' : ''}
              {price.change_pct.toFixed(2)}%
            </span>
            <span className={styles.asOf}>as of {new Date(price.timestamp).toLocaleString()}</span>
          </div>
        ) : null}
      </div>

      <div className={styles.actions}>
        {watchlist.hasWatchlist ? (
          <Button
            variant={watchlist.isInWatchlist ? 'secondary' : 'primary'}
            size="sm"
            onClick={watchlist.isInWatchlist ? watchlist.remove : watchlist.add}
            isLoading={watchlist.isMutating}
          >
            {watchlist.isInWatchlist ? 'Remove from watchlist' : 'Add to watchlist'}
          </Button>
        ) : !watchlist.isLoading ? (
          <span className={styles.watchlistHint}>Create a watchlist to track this symbol</span>
        ) : null}
        <Button variant="secondary" size="sm" onClick={onRefresh} isLoading={isRefreshing}>
          Refresh
        </Button>
      </div>
    </div>
  )
}
