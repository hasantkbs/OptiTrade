import { useState } from 'react'
import { Bar, BarChart, Tooltip as RechartsTooltip, XAxis, YAxis } from 'recharts'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { ChartContainer } from '../../components/ui/ChartContainer'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { SkeletonCard } from '../../components/ui/Skeleton'
import { Tabs } from '../../components/ui/Tabs'
import { Tooltip } from '../../components/ui/Tooltip'
import { useChartColors } from '../../components/ui/useChartColors'
import { useEngineDashboard } from '../dashboard/hooks'
import { apiErrorMessage } from '../../api/client'
import type { EngineAccuracySnapshot, RollingWindow } from '../../api/types'
import styles from './EngineAccuracyPanel.module.css'

const WINDOW_ORDER: RollingWindow[] = ['7d', '30d', '90d', 'lifetime']
const WINDOW_LABEL: Record<RollingWindow, string> = { '7d': '7D', '30d': '30D', '90d': '90D', lifetime: 'Lifetime' }

function EngineAccuracyCard({ engine }: { engine: EngineAccuracySnapshot }) {
  const availableWindows = WINDOW_ORDER.filter((window) => engine.accuracy_by_window[window])
  const [selected, setSelected] = useState<RollingWindow>(availableWindows[0] ?? '30d')
  const colors = useChartColors()
  const metrics = engine.accuracy_by_window[selected]

  const chartData = availableWindows.map((window) => ({
    window: WINDOW_LABEL[window],
    accuracy: engine.accuracy_by_window[window]!.accuracy,
  }))

  if (availableWindows.length === 0) {
    return (
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <span className={styles.engineName}>{engine.engine_name}</span>
          <span className={styles.engineVersion}>v{engine.engine_version}</span>
        </div>
        <p className={styles.unavailable}>No evaluated samples for any rolling window yet.</p>
      </div>
    )
  }

  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <span className={styles.engineName}>{engine.engine_name}</span>
        <span className={styles.engineVersion}>v{engine.engine_version}</span>
      </div>

      <Tabs
        items={availableWindows.map((window) => ({ id: window, label: WINDOW_LABEL[window], content: null }))}
        active={selected}
        onChange={(id) => setSelected(id as RollingWindow)}
      />

      {metrics ? (
        <>
          <div className={styles.metricGrid}>
            <div className={styles.metric}>
              <span className={styles.metricLabel}>Accuracy</span>
              <span className={`num ${styles.metricValue}`}>{(metrics.accuracy * 100).toFixed(1)}%</span>
            </div>
            <div className={styles.metric}>
              <span className={styles.metricLabel}>Precision</span>
              <span className={`num ${styles.metricValue}`}>{(metrics.precision * 100).toFixed(1)}%</span>
            </div>
            <div className={styles.metric}>
              <span className={styles.metricLabel}>Recall</span>
              <span className={`num ${styles.metricValue}`}>{(metrics.recall * 100).toFixed(1)}%</span>
            </div>
            <div className={styles.metric}>
              <Tooltip content="Expected Calibration Error - how far this engine's stated confidence is from its actual accuracy (lower is better calibrated).">
                <span className={styles.metricLabel}>ECE</span>
              </Tooltip>
              <span className={`num ${styles.metricValue}`}>{metrics.calibration_error.toFixed(3)}</span>
            </div>
            <div className={styles.metric}>
              <Tooltip content="Mean absolute error between this engine's expected return and the actual outcome.">
                <span className={styles.metricLabel}>Return MAE</span>
              </Tooltip>
              <span className={`num ${styles.metricValue}`}>{(metrics.expected_return_error * 100).toFixed(2)}%</span>
            </div>
            <div className={styles.metric}>
              <Tooltip content="Mean absolute error between this engine's expected volatility and the actual outcome.">
                <span className={styles.metricLabel}>Volatility MAE</span>
              </Tooltip>
              <span className={`num ${styles.metricValue}`}>{(metrics.volatility_error * 100).toFixed(2)}%</span>
            </div>
          </div>
          <p className={styles.sampleCount}>{metrics.sample_count} evaluated samples in this window</p>
        </>
      ) : null}

      {chartData.length > 1 ? (
        <div className={styles.chartSection}>
          <span className={styles.chartLabel}>Accuracy by window</span>
          <ChartContainer label={`${engine.engine_name} accuracy by rolling window`} height={120} isEmpty={false}>
            <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 24 }}>
              <XAxis type="number" domain={[0, 1]} stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="window" stroke={colors.textSecondary} fontSize={11} tickLine={false} axisLine={false} width={56} />
              <RechartsTooltip
                formatter={(value) => `${(Number(value) * 100).toFixed(1)}%`}
                contentStyle={{ background: colors.border, border: 'none', borderRadius: 6, fontSize: 12 }}
              />
              <Bar dataKey="accuracy" fill={colors.accent} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ChartContainer>
        </div>
      ) : null}
    </div>
  )
}

/**
 * Backed by GET /dashboard/engines (dashboard/models.py::
 * EngineDashboardView.engines[].accuracy_by_window) - real per-window
 * (7d/30d/90d/lifetime) `AccuracyMetrics`, never interpolated between
 * them. Only windows the backend actually returned for that engine are
 * shown as tabs/chart bars (WEB STEP 7 §"Metric windows").
 */
export function EngineAccuracyPanel() {
  const { data, isLoading, isError, error, refetch } = useEngineDashboard()

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Engine accuracy</CardTitle>
          <CardSubtitle>Real evaluated performance per rolling window</CardSubtitle>
        </div>
      </CardHeader>

      {isLoading ? <SkeletonCard /> : null}
      {isError ? <ErrorState message={apiErrorMessage(error)} onRetry={() => void refetch()} /> : null}

      {data ? (
        data.engines.length === 0 ? (
          <EmptyState title="No engines reporting yet" description="Accuracy metrics will appear once engines have evaluated samples." />
        ) : (
          <div className={styles.grid}>
            {data.engines.map((engine) => (
              <EngineAccuracyCard key={`${engine.engine_name}-${engine.engine_version}`} engine={engine} />
            ))}
          </div>
        )
      ) : null}
    </Card>
  )
}
