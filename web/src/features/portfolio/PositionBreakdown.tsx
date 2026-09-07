import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { EmptyState } from '../../components/ui/EmptyState'
import { Table, TableCell, TableHeadCell } from '../../components/ui/Table'
import type { PositionAnalytics } from '../../api/types'

type SortKey = 'symbol' | 'quantity' | 'current_value' | 'weight_pct' | 'unrealized_pnl' | 'unrealized_pnl_pct'
type SortDir = 'asc' | 'desc'

interface PositionBreakdownProps {
  positions: PositionAnalytics[]
  currency: string
}

function formatCurrency(value: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 2 }).format(value)
}

const COLUMNS: { key: SortKey; label: string; align: 'left' | 'right' }[] = [
  { key: 'symbol', label: 'Symbol', align: 'left' },
  { key: 'quantity', label: 'Quantity', align: 'right' },
  { key: 'current_value', label: 'Market value', align: 'right' },
  { key: 'weight_pct', label: 'Weight', align: 'right' },
  { key: 'unrealized_pnl', label: 'Unrealized P&L', align: 'right' },
  { key: 'unrealized_pnl_pct', label: 'Unrealized %', align: 'right' },
]

/**
 * Backed by GET /dashboard/portfolios/{id}'s `positions` field
 * (portfolio/models.py::PositionAnalytics) - every column is a real
 * field on that model; no column (e.g. a "risk" per position) is added
 * unless the backend actually returns it (WEB STEP 3 §7).
 */
export function PositionBreakdown({ positions, currency }: PositionBreakdownProps) {
  const [sortKey, setSortKey] = useState<SortKey>('weight_pct')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const sorted = useMemo(() => {
    const copy = [...positions]
    copy.sort((a, b) => {
      const aVal = a[sortKey]
      const bVal = b[sortKey]
      const cmp = typeof aVal === 'string' ? aVal.localeCompare(bVal as string) : (aVal as number) - (bVal as number)
      return sortDir === 'asc' ? cmp : -cmp
    })
    return copy
  }, [positions, sortKey, sortDir])

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      // Text columns read naturally A→Z first; numeric ones read
      // naturally highest-first.
      setSortDir(key === 'symbol' ? 'asc' : 'desc')
    }
  }

  return (
    <Card padding={positions.length === 0 ? 'default' : 'none'}>
      <div style={positions.length > 0 ? { padding: 'var(--space-5)', paddingBottom: 0 } : undefined}>
        <CardHeader>
          <div>
            <CardTitle>Positions</CardTitle>
            <CardSubtitle>{positions.length} open position{positions.length === 1 ? '' : 's'}</CardSubtitle>
          </div>
        </CardHeader>
      </div>

      {positions.length === 0 ? (
        <EmptyState title="No open positions" description="Positions this portfolio holds will appear here." />
      ) : (
        <Table>
          <thead>
            <tr>
              {COLUMNS.map((col) => (
                <TableHeadCell
                  key={col.key}
                  align={col.align}
                  onClick={() => handleSort(col.key)}
                  aria-sort={sortKey === col.key ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                >
                  {col.label}
                  {sortKey === col.key ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
                </TableHeadCell>
              ))}
              <TableHeadCell>Sector</TableHeadCell>
            </tr>
          </thead>
          <tbody>
            {sorted.map((position) => (
              <tr key={position.symbol}>
                <TableCell numeric>
                  <Link to={`/assets/${position.symbol}`}>{position.symbol}</Link>
                </TableCell>
                <TableCell align="right" numeric>
                  {position.quantity}
                </TableCell>
                <TableCell align="right" numeric>
                  {formatCurrency(position.current_value, position.currency || currency)}
                </TableCell>
                <TableCell align="right" numeric>
                  {position.weight_pct.toFixed(1)}%
                </TableCell>
                <TableCell align="right" numeric>
                  <span style={{ color: position.unrealized_pnl >= 0 ? 'var(--color-positive)' : 'var(--color-negative)' }}>
                    {formatCurrency(position.unrealized_pnl, position.currency || currency)}
                  </span>
                </TableCell>
                <TableCell align="right" numeric>
                  <span style={{ color: position.unrealized_pnl_pct >= 0 ? 'var(--color-positive)' : 'var(--color-negative)' }}>
                    {position.unrealized_pnl_pct.toFixed(1)}%
                  </span>
                </TableCell>
                <TableCell>
                  <Link to="/assets">{position.sector}</Link>
                </TableCell>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  )
}
