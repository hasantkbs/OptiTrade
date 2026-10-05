import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Card, CardHeader, CardTitle } from '../../components/ui/Card'
import { ErrorState } from '../../components/ui/ErrorState'
import { SkeletonCard } from '../../components/ui/Skeleton'
import type { PipelineResponse, Prediction } from '../../api/types'
import styles from './Recommendation.module.css'

const DECISION_TONE: Record<Prediction, 'positive' | 'negative' | 'neutral'> = {
  BUY: 'positive',
  SELL: 'negative',
  HOLD: 'neutral',
}

/** Exact thresholds per this plan's Global Constraints - used verbatim,
 * nowhere else re-derived. */
function confidenceWord(confidence: number): string {
  if (confidence >= 0.66) return 'Yüksek güven'
  if (confidence >= 0.33) return 'Orta güven'
  return 'Düşük güven'
}

interface RecommendationProps {
  data?: PipelineResponse
  isPending: boolean
  isError: boolean
  errorMessage?: string
  onAnalyze: () => void
}

/**
 * Backed entirely by POST /quant/analyze (pipeline/models.py::
 * PipelineResponse), same as the QuantDecision/EngineBreakdown/
 * RiskPanel/ExplanationPanel components this replaces - but shows only
 * `decision`, `explanation` (already plain-language - see
 * ExplanationPanel's own prior docstring), and confidence mapped to a
 * plain word via confidenceWord(). No engine names, no raw confidence
 * %, no expected return/volatility, no "N/M engines succeeded", no
 * evidence list - nothing here is fabricated, every value shown is
 * already in the real response.
 */
export function Recommendation({ data, isPending, isError, errorMessage, onAnalyze }: RecommendationProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recommendation</CardTitle>
        <Button size="sm" onClick={onAnalyze} isLoading={isPending} disabled={isPending}>
          {data ? 'Refresh analysis' : 'Analyze'}
        </Button>
      </CardHeader>

      {isPending && !data ? <SkeletonCard /> : null}

      {isError && !data ? <ErrorState message={errorMessage ?? "Couldn't run the analysis"} onRetry={onAnalyze} /> : null}

      {!isPending && !data && !isError ? (
        <p className={styles.prompt}>Run the analysis to see a recommendation for this symbol.</p>
      ) : null}

      {data ? (
        <div className={styles.body}>
          <div className={styles.row}>
            <Badge tone={DECISION_TONE[data.decision]} className={styles.badge}>
              {data.decision}
            </Badge>
            <span className={styles.confidence}>{confidenceWord(data.confidence)}</span>
          </div>
          {data.explanation ? <p className={styles.explanation}>{data.explanation}</p> : null}
          {isError ? <p className={styles.staleNote}>The last refresh failed - showing the previous result above.</p> : null}
        </div>
      ) : null}
    </Card>
  )
}
