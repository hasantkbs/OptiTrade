import { Badge } from '../../components/ui/Badge'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { SkeletonCard } from '../../components/ui/Skeleton'
import { useLearningDashboard } from '../dashboard/hooks'
import { apiErrorMessage } from '../../api/client'
import styles from './PromotionRecommendationsPanel.module.css'

/**
 * Backed by GET /dashboard/learning's `promotion_candidates`
 * (learning/models.py::PromotionCandidate) - the backend model's own
 * docstring: "a recommendation for a human (or a future automated
 * step) to review, never an automatic promotion." This panel is
 * strictly read-only: no action here can promote, activate, or change
 * any production engine or weight (WEB STEP 7 §"Promotion").
 */
export function PromotionRecommendationsPanel() {
  const { data, isLoading, isError, error, refetch } = useLearningDashboard()
  const candidates = data?.promotion_candidates ?? []

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Promotion recommendations</CardTitle>
          <CardSubtitle>Read-only - review only, never automatic</CardSubtitle>
        </div>
      </CardHeader>

      {isLoading ? <SkeletonCard /> : null}
      {isError ? <ErrorState message={apiErrorMessage(error)} onRetry={() => void refetch()} /> : null}

      {data ? (
        candidates.length === 0 ? (
          <EmptyState
            title="No promotion candidates right now"
            description="Shown when a non-live engine version's accuracy meets or exceeds the live version's by the backend's configured margin."
          />
        ) : (
          <ul className={styles.list}>
            {candidates.map((candidate, index) => (
              <li key={index} className={styles.item}>
                <div className={styles.header}>
                  <span className={styles.engineName}>{candidate.engine_name}</span>
                  <Badge tone="info">{candidate.window}</Badge>
                </div>

                <div className={styles.compareRow}>
                  <span className={styles.compareLabel}>
                    Candidate <span className="num">v{candidate.candidate_version}</span>
                  </span>
                  <div className={styles.barTrack}>
                    <div className={styles.barFillCandidate} style={{ width: `${candidate.candidate_accuracy * 100}%` }} />
                  </div>
                  <span className={`num ${styles.compareValue}`}>{(candidate.candidate_accuracy * 100).toFixed(1)}%</span>
                </div>
                <div className={styles.compareRow}>
                  <span className={styles.compareLabel}>
                    Live <span className="num">v{candidate.live_version}</span>
                  </span>
                  <div className={styles.barTrack}>
                    <div className={styles.barFillLive} style={{ width: `${candidate.live_accuracy * 100}%` }} />
                  </div>
                  <span className={`num ${styles.compareValue}`}>{(candidate.live_accuracy * 100).toFixed(1)}%</span>
                </div>

                <p className={styles.sampleCount}>{candidate.candidate_sample_count} evaluated candidate samples</p>
              </li>
            ))}
          </ul>
        )
      ) : null}

      <p className={styles.disclaimer}>
        A recommendation for human review only - it does not automatically promote, activate, or change any production
        engine or weight.
      </p>
    </Card>
  )
}
