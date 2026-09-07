import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { ErrorState } from '../../components/ui/ErrorState'
import { SkeletonCard } from '../../components/ui/Skeleton'
import { Tooltip } from '../../components/ui/Tooltip'
import type { PipelineResponse, Prediction } from '../../api/types'
import styles from './QuantDecision.module.css'

const DECISION_TONE: Record<Prediction, 'positive' | 'negative' | 'neutral'> = {
  BUY: 'positive',
  SELL: 'negative',
  HOLD: 'neutral',
}

interface QuantDecisionProps {
  data?: PipelineResponse
  isPending: boolean
  isError: boolean
  errorMessage?: string
  onAnalyze: () => void
}

/**
 * Backed entirely by POST /quant/analyze (pipeline/models.py::
 * PipelineResponse) - the sole canonical decision path. This component
 * only ever displays `data.decision`/`confidence`/etc. exactly as
 * returned; no voting, scoring, or recalculation happens here
 * (WEB STEP 4 §5). `decision` is a real 3-way enum (BUY/HOLD/SELL), so
 * HOLD gets the same neutral treatment as any other value - not
 * silently dropped.
 */
export function QuantDecision({ data, isPending, isError, errorMessage, onAnalyze }: QuantDecisionProps) {
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Quant decision</CardTitle>
          <CardSubtitle>Decision Engine output</CardSubtitle>
        </div>
        <Button size="sm" onClick={onAnalyze} isLoading={isPending} disabled={isPending}>
          {data ? 'Refresh analysis' : 'Analyze'}
        </Button>
      </CardHeader>

      {isPending && !data ? <SkeletonCard /> : null}

      {isError && !data ? (
        <ErrorState message={errorMessage ?? "Couldn't run the analysis"} onRetry={onAnalyze} />
      ) : null}

      {!isPending && !data && !isError ? (
        <p className={styles.prompt}>Run the Decision Engine to see a quant decision for this symbol.</p>
      ) : null}

      {data ? (
        <div className={styles.body}>
          <div className={styles.decisionRow}>
            <Badge tone={DECISION_TONE[data.decision]} className={styles.decisionBadge}>
              {data.decision}
            </Badge>
            <div className={styles.metrics}>
              <div className={styles.metric}>
                <span className={styles.label}>Confidence</span>
                <span className={`num ${styles.value}`}>{(data.confidence * 100).toFixed(0)}%</span>
              </div>
              <div className={styles.metric}>
                <Tooltip content="The Decision Engine's expected return for this symbol, as returned by the backend.">
                  <span className={styles.label}>Expected return</span>
                </Tooltip>
                <span className={`num ${styles.value} ${data.expected_return >= 0 ? styles.positive : styles.negative}`}>
                  {data.expected_return >= 0 ? '+' : ''}
                  {(data.expected_return * 100).toFixed(2)}%
                </span>
              </div>
              <div className={styles.metric}>
                <span className={styles.label}>Expected volatility</span>
                <span className={`num ${styles.value}`}>{(data.expected_volatility * 100).toFixed(2)}%</span>
              </div>
            </div>
          </div>

          <div className={styles.metaRow}>
            <span className={styles.metaItem}>As of {new Date(data.metadata.timestamp).toLocaleString()}</span>
            <span className={styles.metaItem}>
              {data.metadata.engines_succeeded}/{data.metadata.engines_available} engines succeeded
            </span>
            {data.metadata.degraded ? <Badge tone="warning">Degraded run</Badge> : null}
          </div>

          {data.evidence.length > 0 ? (
            <div className={styles.evidenceSection}>
              <span className={styles.label}>Supporting evidence</span>
              <ul className={styles.evidenceList}>
                {data.evidence.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {isError ? <p className={styles.staleNote}>The last refresh failed - showing the previous result above.</p> : null}
        </div>
      ) : null}
    </Card>
  )
}
