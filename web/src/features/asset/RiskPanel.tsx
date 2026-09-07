import { Badge } from '../../components/ui/Badge'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { Tooltip } from '../../components/ui/Tooltip'
import type { QuantRiskAssessment } from '../../api/types'
import styles from './RiskPanel.module.css'

const LEVEL_TONE: Record<string, 'positive' | 'warning' | 'negative' | 'neutral'> = {
  LOW: 'positive',
  MEDIUM: 'warning',
  HIGH: 'negative',
}

interface RiskPanelProps {
  risk: QuantRiskAssessment
}

/**
 * Backed entirely by POST /quant/analyze's `risk` field
 * (models/schemas.py::RiskAssessment) - `risk_level` is the backend's
 * own LOW/MEDIUM/HIGH classification, not one invented here. This
 * endpoint has no stop-loss/take-profit/entry-price/ATR/beta/VaR
 * fields, so none are shown (WEB STEP 4 §8, absolute rule).
 */
export function RiskPanel({ risk }: RiskPanelProps) {
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Risk</CardTitle>
          <CardSubtitle>From this quant analysis run</CardSubtitle>
        </div>
      </CardHeader>

      <div className={styles.body}>
        <div className={styles.row}>
          <span className={styles.label}>Risk level</span>
          <Badge tone={LEVEL_TONE[risk.risk_level] ?? 'neutral'}>{risk.risk_level}</Badge>
        </div>
        <div className={styles.row}>
          <span className={styles.label}>Expected volatility</span>
          <span className={`num ${styles.value}`}>{(risk.expected_volatility * 100).toFixed(2)}%</span>
        </div>
        <div className={styles.row}>
          <Tooltip content="How much reliable data was available to compute this analysis (0-1, backend-computed) - not a confidence in the decision itself.">
            <span className={styles.label}>Data sufficiency</span>
          </Tooltip>
          <div className={styles.meterTrack}>
            <div className={styles.meterFill} style={{ width: `${risk.data_sufficiency * 100}%` }} />
          </div>
          <span className={`num ${styles.value}`}>{risk.data_sufficiency.toFixed(2)}</span>
        </div>
      </div>
    </Card>
  )
}
