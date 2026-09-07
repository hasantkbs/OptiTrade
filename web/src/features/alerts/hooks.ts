import { useMutation, useQueryClient } from '@tanstack/react-query'
import { alertsApi } from '../../api/endpoints'
import type { CreateAlertRequest } from '../../api/types'

/**
 * Alert mutations. `useAlerts` (the list read) already lives in
 * features/dashboard/hooks.ts and is reused as-is by the Alerts page -
 * not refetched a second way here. Every mutation invalidates both
 * `['alerts']` and `['dashboard','alerts']` so the Alerts page and the
 * Dashboard's AlertsOverview card never drift out of sync after a
 * create/enable/disable/delete.
 */
function invalidateAlertQueries(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ['alerts'] })
  void queryClient.invalidateQueries({ queryKey: ['dashboard', 'alerts'] })
}

export function useCreateAlert() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CreateAlertRequest) => alertsApi.create(body),
    onSuccess: () => invalidateAlertQueries(queryClient),
  })
}

/** A single shared mutation for every row's enable/disable toggle -
 * `variables` (the alert id being mutated) lets the list disable only
 * the row actually in flight, not the whole table. */
export function useSetAlertEnabled() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ alertId, enabled }: { alertId: number; enabled: boolean }) => alertsApi.setEnabled(alertId, enabled),
    onSuccess: () => invalidateAlertQueries(queryClient),
  })
}

export function useDeleteAlert() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (alertId: number) => alertsApi.remove(alertId),
    onSuccess: () => invalidateAlertQueries(queryClient),
  })
}

/** Does not invalidate `['alerts']` itself - a scan can update
 * `last_checked_at`/`last_triggered_at` on existing alerts, so the list
 * is refreshed too, but the ScanReport result is shown from the
 * mutation's own `data`, never persisted as fake "history". */
export function useScanAlerts() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => alertsApi.scan(),
    onSuccess: () => invalidateAlertQueries(queryClient),
  })
}
