import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import type { AllocationBreakdown } from '../../api/types'
import styles from './CashExposure.module.css'

function formatCurrency(value: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 0 }).format(value)
}

interface CashExposureProps {
  allocation: AllocationBreakdown
  cashBalance: number
  totalValue: number
  currency: string
}

/**
 * `cash_weight_pct` is used exactly as returned by the backend
 * (portfolio/models.py::AllocationBreakdown) - the only derived value
 * here is `investedPct = 100 - cash_weight_pct`, an unambiguous
 * arithmetic complement of a real percentage, and the absolute
 * "invested" amount (`totalValue - cashBalance`), an unambiguous
 * subtraction of two real fields (WEB STEP 3 §10).
 */
export function CashExposure({ allocation, cashBalance, totalValue, currency }: CashExposureProps) {
  const cashPct = allocation.cash_weight_pct
  const investedPct = Math.max(0, 100 - cashPct)
  const investedValue = totalValue - cashBalance

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Cash exposure</CardTitle>
          <CardSubtitle>Cash vs. invested</CardSubtitle>
        </div>
      </CardHeader>

      <div className={styles.bar}>
        <div className={styles.invested} style={{ width: `${investedPct}%` }} />
        <div className={styles.cash} style={{ width: `${cashPct}%` }} />
      </div>

      <div className={styles.legend}>
        <div className={styles.legendItem}>
          <span className={`${styles.swatch} ${styles.investedSwatch}`} />
          <span>Invested {investedPct.toFixed(1)}%</span>
          <span className={`num ${styles.legendValue}`}>{formatCurrency(investedValue, currency)}</span>
        </div>
        <div className={styles.legendItem}>
          <span className={`${styles.swatch} ${styles.cashSwatch}`} />
          <span>Cash {cashPct.toFixed(1)}%</span>
          <span className={`num ${styles.legendValue}`}>{formatCurrency(cashBalance, currency)}</span>
        </div>
      </div>
    </Card>
  )
}
