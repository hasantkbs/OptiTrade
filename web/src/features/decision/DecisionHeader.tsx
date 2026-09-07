import { Button } from '../../components/ui/Button'
import styles from './DecisionHeader.module.css'

interface DecisionHeaderProps {
  onRefresh: () => void
  isRefreshing: boolean
}

/**
 * `onRefresh` only invalidates system-wide, non-rate-limited resources
 * (engine status, watchlist) - it deliberately never re-triggers
 * POST /quant/analyze itself, which has its own explicit "Refresh
 * analysis" action further down the page (WEB STEP 5 §3, §20). No
 * page-wide "last refreshed" timestamp is shown here since the page
 * combines several independently-timestamped resources, each of which
 * already states its own real timestamp where one exists.
 */
export function DecisionHeader({ onRefresh, isRefreshing }: DecisionHeaderProps) {
  return (
    <div className={styles.header}>
      <div>
        <h1 className={styles.title}>Decision Intelligence</h1>
        <p className={styles.subtitle}>
          The decisions produced by the quantitative Decision Engine pipeline for a chosen symbol, and the
          Technical/Fundamental/News engine intelligence, evidence and risk behind each one.
        </p>
      </div>
      <Button variant="secondary" size="sm" onClick={onRefresh} isLoading={isRefreshing}>
        Refresh
      </Button>
    </div>
  )
}
