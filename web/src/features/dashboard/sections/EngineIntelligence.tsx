import { Bar, BarChart, Line, LineChart, Tooltip as RechartsTooltip, XAxis, YAxis } from 'recharts'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../../components/ui/Card'
import { Badge } from '../../../components/ui/Badge'
import { ChartContainer } from '../../../components/ui/ChartContainer'
import { EmptyState } from '../../../components/ui/EmptyState'
import { Tooltip } from '../../../components/ui/Tooltip'
import { useChartColors } from '../../../components/ui/useChartColors'
import { useEngineDashboard } from '../hooks'
import { apiErrorMessage } from '../../../api/client'
import type { DriftType, EngineAccuracySnapshot } from '../../../api/types'
import styles from './EngineIntelligence.module.css'

function formatTime(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const DRIFT_TONE: Record<DriftType, 'positive' | 'info' | 'negative' | 'warning'> = {
  improving: 'positive',
  stable: 'info',
  degrading: 'negative',
  unstable: 'warning',
}

const WINDOW_PREFERENCE = ['30d', '7d', '90d', 'lifetime'] as const

function pickAccuracyWindow(engine: EngineAccuracySnapshot) {
  for (const window of WINDOW_PREFERENCE) {
    const metrics = engine.accuracy_by_window[window]
    if (metrics) return metrics
  }
  return undefined
}

function EngineCard({ engine }: { engine: EngineAccuracySnapshot }) {
  const accuracy = pickAccuracyWindow(engine)
  const weightPct = engine.current_weight != null ? Math.round(engine.current_weight * 100) : null

  return (
    <div className={styles.engineCard}>
      <div className={styles.engineHeader}>
        <span className={styles.engineName}>{engine.engine_name}</span>
        <span className={styles.engineVersion}>v{engine.engine_version}</span>
      </div>

      <div className={styles.metricRow}>
        <Tooltip content="This engine's current contribution to blended Decision Engine output.">
          <span className={styles.metricLabel}>Weight</span>
        </Tooltip>
        {weightPct != null ? (
          <div className={styles.meterTrack}>
            <div className={styles.meterFill} style={{ width: `${weightPct}%` }} />
          </div>
        ) : (
          <span className={styles.unavailable}>—</span>
        )}
        <span className={`num ${styles.metricValue}`}>{weightPct != null ? `${weightPct}%` : 'n/a'}</span>
      </div>

      <div className={styles.metricRow}>
        <Tooltip content="Continuous Learning's evaluated accuracy for this engine - a separate, backward-looking metric from its live weight.">
          <span className={styles.metricLabel}>Accuracy{accuracy ? ` (${accuracy.window})` : ''}</span>
        </Tooltip>
        <span className={`num ${styles.metricValue}`}>
          {accuracy ? `${(accuracy.accuracy * 100).toFixed(1)}%` : 'Not yet evaluated'}
        </span>
      </div>

      <div className={styles.metricRow}>
        <span className={styles.metricLabel}>Drift</span>
        {engine.latest_drift ? (
          <Badge tone={DRIFT_TONE[engine.latest_drift.drift_type]}>{engine.latest_drift.drift_type}</Badge>
        ) : (
          <span className={styles.unavailable}>No signal yet</span>
        )}
      </div>
    </div>
  )
}

/**
 * Backed by GET /dashboard/engines (dashboard/models.py::EngineDashboardView).
 * Deliberately keeps three real but distinct concepts visually separate
 * per WEB STEP 2 §6: `current_weight` (a live Decision Engine value),
 * accuracy (a Continuous Learning-computed, backward-looking metric),
 * and drift status - never blended into one number.
 */
export function EngineIntelligence() {
  const { data, isLoading, isError, error, refetch } = useEngineDashboard()
  const colors = useChartColors()

  const confidencePoints = data?.confidence_history ?? []
  const regimeEntries = Object.entries(data?.regime_distribution ?? {}).map(([regime, count]) => ({ regime, count }))
  const engines = data?.engines ?? []

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Engine intelligence</CardTitle>
          <CardSubtitle>Technical, fundamental &amp; news engines</CardSubtitle>
        </div>
      </CardHeader>

      {isError ? (
        <EmptyState variant="unavailable" title="Couldn't load engine data" description={apiErrorMessage(error)} />
      ) : null}

      {!isError && !isLoading && engines.length === 0 ? (
        <EmptyState title="No engines reporting yet" description="Engine weight, accuracy and drift will appear once the Decision Engine has run." />
      ) : null}

      {!isError && (isLoading || engines.length > 0) ? (
        <div className={styles.engineGrid}>
          {isLoading
            ? Array.from({ length: 3 }).map((_, i) => <div key={i} className={styles.engineCardSkeleton} />)
            : engines.map((engine) => <EngineCard key={`${engine.engine_name}-${engine.engine_version}`} engine={engine} />)}
        </div>
      ) : null}

      <div className={styles.chartsGrid}>
        <div>
          <p className={styles.chartLabel}>Confidence over time</p>
          <ChartContainer
            label="Decision Engine confidence over time"
            height={200}
            isLoading={isLoading}
            error={isError ? apiErrorMessage(error) : null}
            onRetry={() => void refetch()}
            isEmpty={confidencePoints.length === 0}
            emptyTitle="No confidence history yet"
            emptyDescription="Populates once the Decision Engine has recorded confidence scores."
          >
            <LineChart data={confidencePoints.map((p) => ({ ...p, label: formatTime(p.timestamp) }))}>
              <XAxis dataKey="label" stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} width={36} />
              <RechartsTooltip contentStyle={{ background: colors.border, border: 'none', borderRadius: 6, fontSize: 12 }} />
              <Line type="monotone" dataKey="value" stroke={colors.accent} strokeWidth={2} dot={false} />
            </LineChart>
          </ChartContainer>
        </div>

        <div>
          <p className={styles.chartLabel}>Regime distribution</p>
          <ChartContainer
            label="Detected market regime distribution"
            height={200}
            isLoading={isLoading}
            error={isError ? apiErrorMessage(error) : null}
            onRetry={() => void refetch()}
            isEmpty={regimeEntries.length === 0}
            emptyTitle="No regime data yet"
            emptyDescription="Populates once regime scans have run."
          >
            <BarChart data={regimeEntries}>
              <XAxis dataKey="regime" stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} width={28} allowDecimals={false} />
              <RechartsTooltip contentStyle={{ background: colors.border, border: 'none', borderRadius: 6, fontSize: 12 }} />
              <Bar dataKey="count" fill={colors.info} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ChartContainer>
        </div>
      </div>
    </Card>
  )
}
