import { Badge } from '../../components/ui/Badge'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { Tooltip } from '../../components/ui/Tooltip'
import type { Recommendation, RecommendationSeverity, RiskAnalytics as RiskAnalyticsData } from '../../api/types'
import styles from './RiskAnalytics.module.css'

const SEVERITY_TONE: Record<RecommendationSeverity, 'info' | 'warning' | 'negative'> = {
  info: 'info',
  warning: 'warning',
  critical: 'negative',
}

function formatType(type: string) {
  return type.replace(/_/g, ' ')
}

interface RiskAnalyticsProps {
  risk: RiskAnalyticsData | null
  recommendations: Recommendation[]
}

/**
 * Backed by GET /dashboard/portfolios/{id}'s `risk` field
 * (portfolio/models.py::RiskAnalytics) and `recommendations`
 * (portfolio/models.py::Recommendation). `concentration_risk` is
 * genuinely bounded 0-1 by the backend model, so a meter is a valid
 * visualization; unbounded fields (volatility, VaR, CVaR, downside
 * risk) are shown as plain metrics, never as a gauge (WEB STEP 3 §6).
 */
export function RiskAnalytics({ risk, recommendations }: RiskAnalyticsProps) {
  if (!risk) {
    return (
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Risk analytics</CardTitle>
            <CardSubtitle>Volatility, beta &amp; concentration</CardSubtitle>
          </div>
        </CardHeader>
        <p className={styles.unavailable}>Risk analytics have not been computed for this portfolio yet.</p>
      </Card>
    )
  }

  const correlationSymbols = Object.keys(risk.correlation_matrix)
  const visibleSymbols = correlationSymbols.slice(0, 6)

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Risk analytics</CardTitle>
          <CardSubtitle>Volatility, beta &amp; concentration</CardSubtitle>
        </div>
      </CardHeader>

      <div className={styles.metricGrid}>
        <div className={styles.metric}>
          <span className={styles.metricLabel}>Volatility</span>
          <span className={`num ${styles.metricValue}`}>{risk.volatility_pct.toFixed(1)}%</span>
        </div>
        <div className={styles.metric}>
          <span className={styles.metricLabel}>Beta</span>
          <span className={`num ${styles.metricValue}`}>{risk.beta != null ? risk.beta.toFixed(2) : '—'}</span>
        </div>
        <div className={styles.metric}>
          <span className={styles.metricLabel}>VaR (95%)</span>
          <span className={`num ${styles.metricValue}`}>{risk.var_95_pct.toFixed(1)}%</span>
        </div>
        <div className={styles.metric}>
          <span className={styles.metricLabel}>CVaR (95%)</span>
          <span className={`num ${styles.metricValue}`}>{risk.cvar_95_pct.toFixed(1)}%</span>
        </div>
        <div className={styles.metric}>
          <span className={styles.metricLabel}>Downside risk</span>
          <span className={`num ${styles.metricValue}`}>{risk.downside_risk_pct.toFixed(1)}%</span>
        </div>
      </div>

      <div className={styles.meterRow}>
        <Tooltip content="A 0-1 score describing how concentrated this portfolio's value is in a small number of holdings, computed by the backend's risk analytics engine. Higher means more concentrated in fewer positions.">
          <span className={styles.meterLabel}>Concentration</span>
        </Tooltip>
        <div className={styles.meterTrack}>
          <div className={styles.meterFill} style={{ width: `${risk.concentration_risk * 100}%` }} />
        </div>
        <span className={`num ${styles.meterValue}`}>{risk.concentration_risk.toFixed(2)}</span>
      </div>

      {visibleSymbols.length >= 2 ? (
        <div className={styles.correlationSection}>
          <span className={styles.sectionLabel}>Correlation matrix{correlationSymbols.length > 6 ? ` (first 6 of ${correlationSymbols.length})` : ''}</span>
          <div className={styles.correlationScroller}>
            <table className={styles.correlationTable}>
              <thead>
                <tr>
                  <th />
                  {visibleSymbols.map((symbol) => (
                    <th key={symbol} className="num">
                      {symbol}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibleSymbols.map((rowSymbol) => (
                  <tr key={rowSymbol}>
                    <th className="num">{rowSymbol}</th>
                    {visibleSymbols.map((colSymbol) => (
                      <td key={colSymbol} className="num">
                        {risk.correlation_matrix[rowSymbol]?.[colSymbol]?.toFixed(2) ?? '—'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      <div className={styles.recommendationsSection}>
        <span className={styles.sectionLabel}>Recommendations</span>
        {recommendations.length === 0 ? (
          <p className={styles.emptyRecommendations}>No recommendations right now.</p>
        ) : (
          <ul className={styles.recommendationsList}>
            {recommendations.map((rec, index) => (
              <li key={index} className={styles.recommendationItem}>
                <div className={styles.recommendationHeader}>
                  <Badge tone={SEVERITY_TONE[rec.severity]}>{formatType(rec.recommendation_type)}</Badge>
                  {rec.symbol ? <span className="num">{rec.symbol}</span> : null}
                </div>
                <p className={styles.recommendationMessage}>{rec.message}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  )
}
