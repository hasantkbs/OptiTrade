import { Card, CardHeader, CardTitle } from '../../components/ui/Card'
import { Tooltip } from '../../components/ui/Tooltip'
import styles from './Diversification.module.css'

interface DiversificationProps {
  score: number | null
}

/**
 * Backed by GET /dashboard/portfolios/{id}'s `risk.diversification_score`
 * (portfolio/models.py::RiskAnalytics.diversification_score, bounded
 * 0.0-1.0 by the backend model itself). Presented as the raw score with
 * an explanatory tooltip describing what the bounds mean - no invented
 * qualitative label like "good" or "poor" (WEB STEP 3 §11).
 */
export function Diversification({ score }: DiversificationProps) {
  return (
    <Card>
      <CardHeader>
        <div>
          <Tooltip content="A 0-1 score reflecting how evenly this portfolio's value is spread across positions, computed by the backend's risk analytics engine. 0 means fully concentrated in one holding; 1 means maximally spread out.">
            <CardTitle>Diversification</CardTitle>
          </Tooltip>
        </div>
      </CardHeader>

      {score == null ? (
        <p className={styles.unavailable}>Not yet computed for this portfolio.</p>
      ) : (
        <div className={styles.body}>
          <span className={`num ${styles.score}`}>{score.toFixed(2)}</span>
          <div className={styles.track}>
            <div className={styles.fill} style={{ width: `${score * 100}%` }} />
          </div>
          <div className={styles.scaleLabels}>
            <span>Concentrated</span>
            <span>Diversified</span>
          </div>
        </div>
      )}
    </Card>
  )
}
