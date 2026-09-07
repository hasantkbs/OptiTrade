import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { Badge } from '../../components/ui/Badge'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { SkeletonCard } from '../../components/ui/Skeleton'
import { Table, TableCell, TableHeadCell } from '../../components/ui/Table'
import { apiErrorMessage } from '../../api/client'
import type { TransactionType } from '../../api/types'
import { usePortfolioTransactions } from './hooks'

const TYPE_TONE: Record<TransactionType, 'positive' | 'negative' | 'info' | 'warning' | 'neutral'> = {
  deposit: 'positive',
  withdrawal: 'negative',
  buy: 'info',
  sell: 'warning',
  dividend: 'positive',
  fee: 'neutral',
  tax: 'neutral',
}

interface RecentActivityProps {
  portfolioId: number
}

function formatCurrency(value: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 2 }).format(value)
}

/**
 * Backed by GET /portfolios/{id}/history (portfolio/models.py::
 * Transaction) - the real ledger of deposits, withdrawals, trades and
 * dividends. This is genuine historical data (unlike the equity/P&L
 * time series discussed in PerformanceHistory/DrawdownAnalysis, which
 * has no read endpoint at all) - sorted newest-first for a "recent
 * activity" feed since the backend doesn't guarantee an order. Each
 * row formats using that transaction's own `currency` field rather
 * than the portfolio's base currency, since a transaction can be
 * recorded in a different one.
 */
export function RecentActivity({ portfolioId }: RecentActivityProps) {
  const { data, isLoading, isError, error, refetch } = usePortfolioTransactions(portfolioId)
  const sorted = [...(data ?? [])].sort((a, b) => new Date(b.executed_at).getTime() - new Date(a.executed_at).getTime())

  return (
    <Card padding={sorted.length === 0 ? 'default' : 'none'}>
      <div style={sorted.length > 0 ? { padding: 'var(--space-5)', paddingBottom: 0 } : undefined}>
        <CardHeader>
          <div>
            <CardTitle>Recent activity</CardTitle>
            <CardSubtitle>Deposits, withdrawals &amp; trades</CardSubtitle>
          </div>
        </CardHeader>
      </div>

      {isLoading ? <SkeletonCard /> : null}
      {isError ? <ErrorState message={apiErrorMessage(error)} onRetry={() => void refetch()} /> : null}

      {!isLoading && !isError && sorted.length === 0 ? (
        <EmptyState title="No activity yet" description="Deposits, withdrawals, trades and dividends will appear here." />
      ) : null}

      {!isLoading && !isError && sorted.length > 0 ? (
        <Table>
          <thead>
            <tr>
              <TableHeadCell>Type</TableHeadCell>
              <TableHeadCell>Symbol</TableHeadCell>
              <TableHeadCell align="right">Quantity</TableHeadCell>
              <TableHeadCell align="right">Price</TableHeadCell>
              <TableHeadCell align="right">Amount</TableHeadCell>
              <TableHeadCell align="right">Executed</TableHeadCell>
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, 10).map((tx) => (
              <tr key={tx.id}>
                <TableCell>
                  <Badge tone={TYPE_TONE[tx.transaction_type]}>{tx.transaction_type}</Badge>
                </TableCell>
                <TableCell numeric>{tx.symbol ?? '—'}</TableCell>
                <TableCell align="right" numeric>
                  {tx.quantity ?? '—'}
                </TableCell>
                <TableCell align="right" numeric>
                  {tx.price != null ? formatCurrency(tx.price, tx.currency) : '—'}
                </TableCell>
                <TableCell align="right" numeric>
                  {formatCurrency(tx.amount, tx.currency)}
                </TableCell>
                <TableCell align="right">{new Date(tx.executed_at).toLocaleDateString()}</TableCell>
              </tr>
            ))}
          </tbody>
        </Table>
      ) : null}
    </Card>
  )
}
