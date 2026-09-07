import { useOverview } from './hooks'

export type SystemStatus = 'live' | 'degraded' | 'offline'

/**
 * The header's status readout used to be a hardcoded "live" string
 * (WEB STEP 1) - a fabricated indicator, exactly what WEB STEP 2 §16
 * forbids. It now reflects the real fetch state of the dashboard's own
 * primary query (/dashboard/overview): successful -> live, still
 * loading for the first time -> degraded (not yet confirmed reachable,
 * not a failure either), errored -> offline. No separate health-check
 * endpoint call is introduced - the overview request the dashboard is
 * already making is the honest signal.
 */
export function useSystemStatus(): SystemStatus {
  const { isError, isSuccess } = useOverview()
  if (isError) return 'offline'
  if (isSuccess) return 'live'
  return 'degraded'
}
