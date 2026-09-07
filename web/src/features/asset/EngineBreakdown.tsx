import { Badge } from '../../components/ui/Badge'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { EmptyState } from '../../components/ui/EmptyState'
import type { EngineBreakdownItem, EngineExecutionStatus, Prediction } from '../../api/types'
import styles from './EngineBreakdown.module.css'

const STATUS_TONE: Record<EngineExecutionStatus, 'positive' | 'negative' | 'warning' | 'neutral'> = {
  success: 'positive',
  timeout: 'warning',
  failed: 'negative',
  invalid: 'neutral',
}

const PREDICTION_TONE: Record<Prediction, 'positive' | 'negative' | 'neutral'> = {
  BUY: 'positive',
  SELL: 'negative',
  HOLD: 'neutral',
}

function formatEngineName(name: string) {
  const withoutSuffix = name.endsWith('Engine') ? name.slice(0, -'Engine'.length) : name
  return withoutSuffix.replace(/([a-z0-9])([A-Z])/g, '$1 $2')
}

function EngineCard({ engine }: { engine: EngineBreakdownItem }) {
  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <div>
          <span className={styles.engineName}>{formatEngineName(engine.engine_name)}</span>
          <span className={styles.engineVersion}>v{engine.engine_version}</span>
        </div>
        <Badge tone={STATUS_TONE[engine.status]}>{engine.status}</Badge>
      </div>

      {engine.prediction ? (
        <div className={styles.row}>
          <span className={styles.rowLabel}>Vote</span>
          <Badge tone={PREDICTION_TONE[engine.prediction]}>{engine.prediction}</Badge>
        </div>
      ) : null}

      {engine.confidence != null ? (
        <div className={styles.row}>
          <span className={styles.rowLabel}>Confidence</span>
          <div className={styles.meterTrack}>
            <div className={styles.meterFill} style={{ width: `${engine.confidence * 100}%` }} />
          </div>
          <span className={`num ${styles.rowValue}`}>{(engine.confidence * 100).toFixed(0)}%</span>
        </div>
      ) : null}

      {engine.expected_return != null || engine.volatility != null ? (
        <div className={styles.statsRow}>
          {engine.expected_return != null ? (
            <span>
              Exp. return <span className="num">{(engine.expected_return * 100).toFixed(2)}%</span>
            </span>
          ) : null}
          {engine.volatility != null ? (
            <span>
              Volatility <span className="num">{(engine.volatility * 100).toFixed(2)}%</span>
            </span>
          ) : null}
        </div>
      ) : null}

      {engine.evidence.length > 0 ? (
        <ul className={styles.evidenceList}>
          {engine.evidence.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      ) : engine.status === 'success' ? (
        <p className={styles.noEvidence}>No supporting evidence returned.</p>
      ) : null}
    </div>
  )
}

interface EngineBreakdownProps {
  engines: EngineBreakdownItem[]
}

/**
 * Backed by POST /quant/analyze's `engine_breakdown` field
 * (models/schemas.py::EngineBreakdownItem via pipeline/models.py). Each
 * item's own `engine_name` decides how many cards render (3 fixed
 * engines plus any active Model Serving models) - nothing here assumes
 * exactly Technical/Fundamental/News. `evidence` is the backend's own
 * free-text list; nothing here manufactures a per-indicator value the
 * response doesn't actually contain (WEB STEP 4 §6, §9).
 */
export function EngineBreakdown({ engines }: EngineBreakdownProps) {
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Engine intelligence</CardTitle>
          <CardSubtitle>Technical, fundamental &amp; news engines</CardSubtitle>
        </div>
      </CardHeader>

      {engines.length === 0 ? (
        <EmptyState title="No engine data yet" description="Run the analysis above to see each engine's contribution." />
      ) : (
        <div className={styles.grid}>
          {engines.map((engine) => (
            <EngineCard key={`${engine.engine_name}-${engine.engine_version}`} engine={engine} />
          ))}
        </div>
      )}
    </Card>
  )
}
