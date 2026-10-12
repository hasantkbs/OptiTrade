import { useState } from 'react'
import axios from 'axios'
import { Link } from 'react-router-dom'
import { Badge } from '../../components/ui/Badge'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { SkeletonCard } from '../../components/ui/Skeleton'
import { Table, TableCell, TableHeadCell } from '../../components/ui/Table'
import { Tabs, type TabItem } from '../../components/ui/Tabs'
import { Tooltip } from '../../components/ui/Tooltip'
import { apiErrorMessage } from '../../api/client'
import type { MarketOpportunityItem, OpportunityLabel } from '../../api/types'
import { useMarketOpportunities, type SearchableMarket } from './hooks'

const MARKET_TABS: { id: SearchableMarket; label: string }[] = [
  { id: 'TR', label: 'BIST (TR)' },
  { id: 'US', label: 'US' },
  { id: 'CRYPTO', label: 'Crypto' },
]

const LABEL_DISPLAY: Record<OpportunityLabel, { text: string; tone: 'positive' | 'neutral' | 'warning' | 'negative' }> = {
  STRONG_BUY_BIAS: { text: 'Strong Buy', tone: 'positive' },
  BUY_BIAS: { text: 'Buy', tone: 'positive' },
  HOLD: { text: 'Hold', tone: 'neutral' },
  WATCH: { text: 'Watch', tone: 'warning' },
  RISK_DETERIORATING: { text: 'Risk deteriorating', tone: 'negative' },
}

/** The Market page's "top opportunities" picker - scans a whole
 * market's symbol universe through the real decision pipeline and
 * ranks it (intelligence.opportunity_ranking, already-built Phase C/D
 * primitives - no new scoring here), refreshed server-side every 5
 * minutes. */
export function MarketOpportunities() {
  const [market, setMarket] = useState<SearchableMarket>('US')

  const items: TabItem[] = MARKET_TABS.map((tab) => ({
    id: tab.id,
    label: tab.label,
    content: <MarketOpportunitiesList market={tab.id} />,
  }))

  return <Tabs items={items} active={market} onChange={(id) => setMarket(id as SearchableMarket)} />
}

function MarketOpportunitiesList({ market }: { market: SearchableMarket }) {
  const { data, isLoading, isError, error, refetch } = useMarketOpportunities(market)

  if (isLoading) {
    return <SkeletonCard />
  }

  if (isError) {
    const notReadyYet = axios.isAxiosError(error) && error.response?.status === 503
    return notReadyYet ? (
      <EmptyState
        title="Still analyzing this market"
        description="The model is scanning this market's symbols now - this usually takes a few minutes. Check back shortly."
      />
    ) : (
      <ErrorState message={apiErrorMessage(error)} onRetry={() => void refetch()} />
    )
  }

  if (!data || data.opportunities.length === 0) {
    return <EmptyState title="No opportunities yet" description="Nothing ranked for this market yet." />
  }

  return (
    <Table>
      <thead>
        <tr>
          <TableHeadCell align="right">#</TableHeadCell>
          <TableHeadCell>Symbol</TableHeadCell>
          <TableHeadCell>Model view</TableHeadCell>
          <TableHeadCell align="right">
            <Tooltip content="How confident the model is in this decision, 0-100%.">Confidence</Tooltip>
          </TableHeadCell>
          <TableHeadCell align="right">
            <Tooltip content="The model's expected price change, as a percentage.">Expected return</Tooltip>
          </TableHeadCell>
          <TableHeadCell align="right">Risk</TableHeadCell>
        </tr>
      </thead>
      <tbody>
        {data.opportunities.map((item) => (
          <OpportunityRow key={item.symbol} item={item} />
        ))}
      </tbody>
    </Table>
  )
}

function OpportunityRow({ item }: { item: MarketOpportunityItem }) {
  const label = LABEL_DISPLAY[item.label]
  return (
    <tr>
      <TableCell align="right" numeric>
        {item.rank}
      </TableCell>
      <TableCell>
        <Link to={`/assets/${item.symbol}`}>{item.symbol}</Link>
      </TableCell>
      <TableCell>
        <Badge tone={label.tone}>{label.text}</Badge>
      </TableCell>
      <TableCell align="right" numeric>
        {(item.confidence * 100).toFixed(0)}%
      </TableCell>
      <TableCell align="right" numeric>
        {(item.expected_return * 100).toFixed(2)}%
      </TableCell>
      <TableCell align="right">{item.risk_bucket}</TableCell>
    </tr>
  )
}
