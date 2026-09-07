import { Card, CardHeader, CardSubtitle, CardTitle } from '../../../components/ui/Card'
import { EmptyState } from '../../../components/ui/EmptyState'

/**
 * No endpoint currently exposes a Decision Engine execution feed
 * (checked: no /decision*, /execution* route in main.py, and
 * decision_engine_executions is written but never read back via the
 * API). Per WEB STEP 1 §5, this is shown honestly rather than
 * fabricated - wiring this up is a backend task for a later step.
 */
export function RecentDecisionsSection() {
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Recent decisions</CardTitle>
          <CardSubtitle>Latest Decision Engine executions</CardSubtitle>
        </div>
      </CardHeader>
      <EmptyState
        variant="unavailable"
        title="Not available yet"
        description="The backend doesn't currently expose a decision execution feed over the API. This section will connect once that endpoint exists."
      />
    </Card>
  )
}
