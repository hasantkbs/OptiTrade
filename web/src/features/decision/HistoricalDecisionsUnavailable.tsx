import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { EmptyState } from '../../components/ui/EmptyState'

/**
 * Verified against the current backend (decision_engine/repository.py,
 * pipeline/pipeline.py): every /quant/analyze call already persists its
 * full decision (symbol, decision, confidence, expected_return,
 * expected_volatility, evidence, engine_results, timestamp) to the
 * `decision_engine_executions` table, and a `get_recent(symbol, limit)`
 * repository method to read it back already exists - but no FastAPI
 * route anywhere calls it. There is no GET endpoint for historical
 * decisions, so this is an honest unavailable state rather than a
 * fabricated history table (WEB STEP 5 §10).
 */
export function HistoricalDecisionsUnavailable() {
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Historical decision intelligence</CardTitle>
          <CardSubtitle>Recent decisions, filtering &amp; outcome tracking</CardSubtitle>
        </div>
      </CardHeader>
      <EmptyState
        variant="unavailable"
        title="Historical decision tracking is not currently exposed by the backend"
        description="Every analysis is already recorded internally, but no API endpoint returns that history yet. Exposing it would require a read endpoint over the existing decision record (symbol, decision, confidence, evidence, engine votes, timestamp) - and a true win rate or P&L would additionally require the backend to track each decision's real outcome against later price movement, which it does not currently compute."
      />
    </Card>
  )
}
