import { Card, CardHeader, CardSubtitle, CardTitle } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import styles from './ResearchPage.module.css'

interface ResearchCapability {
  title: string
  description: string
}

const CAPABILITIES: ResearchCapability[] = [
  { title: 'Experiments', description: 'No endpoint exists to list, create, or read Research Lab experiments.' },
  { title: 'Hypotheses', description: 'No endpoint exists to read the hypothesis registry.' },
  { title: 'Backtests', description: 'No endpoint exists to run or read backtest results from this system.' },
  { title: 'Benchmarks', description: 'No endpoint exists to read benchmark comparisons.' },
  { title: 'Feature analysis', description: 'No endpoint exists to read feature importance, drift, or statistics.' },
  { title: 'Model analysis', description: 'No endpoint exists to read model diagnostics or comparisons.' },
  { title: 'Shadow results', description: "Research Lab's own shadow evaluation results have no read endpoint (distinct from Continuous Learning's shadow samples, shown on the Learning page)." },
  { title: 'Promotion recommendations', description: 'No endpoint exists to read Research Lab promotion recommendations.' },
  { title: 'Reports', description: 'No endpoint exists to read generated research reports.' },
]

/**
 * /research - the backend's `research_lab` package (experiments,
 * hypothesis, backtesting, benchmarking, feature_analysis,
 * model_analysis, datasets, shadow, promotion, reports subpackages -
 * verified to exist in the repository) is never imported by main.py
 * and has zero HTTP routes anywhere in the backend (verified: no
 * `include_router` or route decorator references it) - confirmed
 * still true for WEB STEP 7. `research_lab/service.py`'s own docstring
 * states the design intent directly: "This is a fully isolated,
 * offline research environment... Nothing reachable from this facade
 * ever executes against or mutates production inference." This page
 * makes that isolation and the resulting lack of a frontend-safe API
 * explicit per capability, rather than fabricating experiment/backtest
 * data or calling internal backend code directly.
 */
export function ResearchPage() {
  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Research Lab</h1>
        <p className={styles.subtitle}>
          The backend's Research Lab is a fully isolated, offline research environment - nothing it does executes
          against or mutates production inference. It currently has no HTTP API, so nothing from it is reachable from
          this app.
        </p>
      </div>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>Production vs. research</CardTitle>
            <CardSubtitle>Even if this became available, it would never drive production decisions</CardSubtitle>
          </div>
        </CardHeader>
        <p className={styles.isolationNote}>
          Research results are architecturally isolated from the live Decision Engine pipeline behind{' '}
          <code className={styles.code}>/quant/analyze</code>. Any future promotion capability would surface a
          recommendation for a human to review - the same read-only pattern already used for Continuous Learning's
          promotion candidates on the Learning page - never an automatic change to a production engine or weight.
        </p>
      </Card>

      <div className={styles.grid}>
        {CAPABILITIES.map((capability) => (
          <Card key={capability.title}>
            <EmptyState variant="unavailable" title={capability.title} description={capability.description} />
          </Card>
        ))}
      </div>
    </div>
  )
}
