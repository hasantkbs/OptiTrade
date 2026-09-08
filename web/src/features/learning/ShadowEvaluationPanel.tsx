import { Badge } from '../../components/ui/Badge'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { SkeletonCard } from '../../components/ui/Skeleton'
import { useLearningDashboard } from '../dashboard/hooks'
import { apiErrorMessage } from '../../api/client'
import type { LearningSampleSnapshot, Prediction } from '../../api/types'
import styles from './ShadowEvaluationPanel.module.css'

const DECISION_TONE: Record<Prediction, 'positive' | 'negative' | 'neutral'> = {
  BUY: 'positive',
  SELL: 'negative',
  HOLD: 'neutral',
}

function SampleList({ samples }: { samples: LearningSampleSnapshot[] }) {
  if (samples.length === 0) {
    return <p className={styles.empty}>None in this list.</p>
  }
  return (
    <ul className={styles.list}>
      {samples.map((sample, index) => (
        <li key={index} className={styles.row}>
          <span className={`num ${styles.symbol}`}>{sample.symbol}</span>
          <Badge tone={DECISION_TONE[sample.decision]}>{sample.decision}</Badge>
          <span className="num">{(sample.confidence * 100).toFixed(0)}%</span>
          <span className={styles.time}>{new Date(sample.decided_at).toLocaleDateString()}</span>
          {sample.evaluated ? (
            <Badge tone={sample.correct ? 'positive' : 'negative'}>{sample.correct ? 'Correct' : 'Incorrect'}</Badge>
          ) : (
            <span className={styles.pending}>Pending evaluation</span>
          )}
        </li>
      ))}
    </ul>
  )
}

/**
 * Backed by GET /dashboard/learning's `recent_samples`
 * (dashboard/models.py::LearningSampleSnapshot) - `source` is the real
 * live/shadow distinction (learning/models.py::SampleSource). Shadow
 * samples are visually and structurally separated from production ones
 * here, never merged into one list - per model_serving/shadow.py's own
 * guarantee, a shadow evaluation never influences a live decision
 * (WEB STEP 7 §"Shadow evaluation").
 */
export function ShadowEvaluationPanel() {
  const { data, isLoading, isError, error, refetch } = useLearningDashboard()
  const samples = data?.recent_samples ?? []
  const live = samples.filter((s) => s.source === 'live')
  const shadow = samples.filter((s) => s.source === 'shadow')

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Shadow evaluation</CardTitle>
          <CardSubtitle>Recent samples - shadow results never affect production decisions</CardSubtitle>
        </div>
      </CardHeader>

      {isLoading ? <SkeletonCard /> : null}
      {isError ? <ErrorState message={apiErrorMessage(error)} onRetry={() => void refetch()} /> : null}

      {data ? (
        samples.length === 0 ? (
          <EmptyState title="No recent samples yet" description="Live and shadow samples will appear here once the Decision Engine has run." />
        ) : (
          <div className={styles.columns}>
            <div className={styles.column}>
              <div className={styles.columnHeader}>
                <Badge tone="neutral">Production</Badge>
                <span className="num">{live.length}</span>
              </div>
              <SampleList samples={live} />
            </div>
            <div className={styles.column}>
              <div className={styles.columnHeader}>
                <Badge tone="info">Shadow</Badge>
                <span className="num">{shadow.length}</span>
              </div>
              <SampleList samples={shadow} />
            </div>
          </div>
        )
      ) : null}
    </Card>
  )
}
