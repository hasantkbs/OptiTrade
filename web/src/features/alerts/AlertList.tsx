import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { ConfirmDialog } from '../../components/ui/ConfirmDialog'
import { EmptyState } from '../../components/ui/EmptyState'
import { Table, TableCell, TableHeadCell } from '../../components/ui/Table'
import { apiErrorMessage } from '../../api/client'
import type { Alert } from '../../api/types'
import { useDeleteAlert, useSetAlertEnabled } from './hooks'
import { formatAlertType } from './alertTypes'
import styles from './AlertList.module.css'

function formatParameters(parameters: Record<string, number>) {
  const entries = Object.entries(parameters)
  if (entries.length === 0) return '—'
  return entries.map(([key, value]) => `${key}: ${value}`).join(', ')
}

interface AlertListProps {
  alerts: Alert[]
}

/**
 * Every column is a real field on watchlist/models.py::Alert - no
 * fabricated "status"/"severity" column (severity only exists on a
 * `AlertTriggerEvent`, which is scan output, not a property of the
 * alert configuration itself - see ScanPanel for that). Enable/disable
 * uses the real PATCH /alerts/{id}/enabled; delete requires an explicit
 * confirmation and uses the real DELETE /alerts/{id} (WEB STEP 6).
 */
export function AlertList({ alerts }: AlertListProps) {
  const setEnabled = useSetAlertEnabled()
  const deleteAlert = useDeleteAlert()
  const [pendingDelete, setPendingDelete] = useState<Alert | null>(null)

  if (alerts.length === 0) {
    return (
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Your alerts</CardTitle>
            <CardSubtitle>Configured price, technical, decision, news &amp; portfolio alerts</CardSubtitle>
          </div>
        </CardHeader>
        <EmptyState title="No alerts configured" description="Alerts you create will appear here." />
      </Card>
    )
  }

  return (
    <Card padding="none">
      <div style={{ padding: 'var(--space-5)', paddingBottom: 0 }}>
        <CardHeader>
          <div>
            <CardTitle>Your alerts</CardTitle>
            <CardSubtitle>{alerts.length} configured</CardSubtitle>
          </div>
        </CardHeader>
        {setEnabled.isError ? <p className={styles.mutationError}>{apiErrorMessage(setEnabled.error)}</p> : null}
        {deleteAlert.isError ? <p className={styles.mutationError}>{apiErrorMessage(deleteAlert.error)}</p> : null}
      </div>

      <Table>
        <thead>
          <tr>
            <TableHeadCell>Symbol / target</TableHeadCell>
            <TableHeadCell>Type</TableHeadCell>
            <TableHeadCell>Parameters</TableHeadCell>
            <TableHeadCell>Created</TableHeadCell>
            <TableHeadCell>Last triggered</TableHeadCell>
            <TableHeadCell align="right">Enabled</TableHeadCell>
            <TableHeadCell align="right">Actions</TableHeadCell>
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert) => {
            const isTogglePending = setEnabled.isPending && setEnabled.variables?.alertId === alert.id
            return (
              <tr key={alert.id}>
                <TableCell numeric>
                  {alert.symbol ? (
                    <Link to={`/assets/${alert.symbol}`}>{alert.symbol}</Link>
                  ) : alert.portfolio_id != null ? (
                    `Portfolio #${alert.portfolio_id}`
                  ) : (
                    '—'
                  )}
                </TableCell>
                <TableCell>{formatAlertType(alert.alert_type)}</TableCell>
                <TableCell>
                  <span className="num">{formatParameters(alert.parameters)}</span>
                </TableCell>
                <TableCell>{new Date(alert.created_at).toLocaleDateString()}</TableCell>
                <TableCell>{alert.last_triggered_at ? new Date(alert.last_triggered_at).toLocaleString() : 'Never'}</TableCell>
                <TableCell align="right">
                  <div className={styles.enabledCell}>
                    <Badge tone={alert.enabled ? 'positive' : 'neutral'}>{alert.enabled ? 'Enabled' : 'Disabled'}</Badge>
                    <Button
                      size="sm"
                      variant="secondary"
                      isLoading={isTogglePending}
                      disabled={isTogglePending}
                      onClick={() => setEnabled.mutate({ alertId: alert.id as number, enabled: !alert.enabled })}
                    >
                      {alert.enabled ? 'Disable' : 'Enable'}
                    </Button>
                  </div>
                </TableCell>
                <TableCell align="right">
                  <div className={styles.actions}>
                    {alert.category === 'decision' && alert.symbol ? (
                      <Link to={`/assets/${alert.symbol}`} className={styles.decisionLink}>
                        View recommendation →
                      </Link>
                    ) : null}
                    <Button size="sm" variant="danger" onClick={() => setPendingDelete(alert)}>
                      Delete
                    </Button>
                  </div>
                </TableCell>
              </tr>
            )
          })}
        </tbody>
      </Table>

      <ConfirmDialog
        open={pendingDelete != null}
        title="Delete this alert?"
        description={pendingDelete ? `This permanently deletes the ${formatAlertType(pendingDelete.alert_type)} alert${pendingDelete.symbol ? ` for ${pendingDelete.symbol}` : ''}.` : undefined}
        confirmLabel="Delete"
        destructive
        isConfirming={deleteAlert.isPending}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete?.id != null) {
            deleteAlert.mutate(pendingDelete.id, { onSuccess: () => setPendingDelete(null) })
          }
        }}
      />
    </Card>
  )
}
