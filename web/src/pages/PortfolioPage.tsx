import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { SkeletonCard } from '../components/ui/Skeleton'
import { apiErrorMessage } from '../api/client'
import { usePortfolioDashboard, usePortfolioList } from '../features/dashboard/hooks'
import { useRefreshPortfolio } from '../features/portfolio/hooks'
import { AddCashDialog } from '../features/portfolio/AddCashDialog'
import { AddPositionDialog } from '../features/portfolio/AddPositionDialog'
import { CreatePortfolioDialog } from '../features/portfolio/CreatePortfolioDialog'
import { PortfolioHeader } from '../features/portfolio/PortfolioHeader'
import { PortfolioSummary } from '../features/portfolio/PortfolioSummary'
import { AllocationAnalysis } from '../features/portfolio/AllocationAnalysis'
import { PositionBreakdown } from '../features/portfolio/PositionBreakdown'
import { PerformanceHistory } from '../features/portfolio/PerformanceHistory'
import { DrawdownAnalysis } from '../features/portfolio/DrawdownAnalysis'
import { CashExposure } from '../features/portfolio/CashExposure'
import { Diversification } from '../features/portfolio/Diversification'
import { RiskAnalytics } from '../features/portfolio/RiskAnalytics'
import { RecentActivity } from '../features/portfolio/RecentActivity'
import styles from './PortfolioPage.module.css'

/**
 * Backed by GET /portfolios (selector) + GET /dashboard/portfolios/{id}
 * (everything else - portfolio/models.py::PortfolioDashboard, fetched
 * once here and passed down as props so every section below is a pure
 * presentational component, not a second fetcher of the same
 * resource). The selected portfolio id lives in the URL (`?id=`) so it
 * survives a refresh/share, and because `usePortfolioDashboard` keys
 * its query by that id, switching portfolios can never let a slow,
 * stale response for the previously-selected portfolio overwrite the
 * newly-selected one's data (WEB STEP 3 §3, §17).
 */
export function PortfolioPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [createOpen, setCreateOpen] = useState(false)
  const [addPositionOpen, setAddPositionOpen] = useState(false)
  const [addCashOpen, setAddCashOpen] = useState(false)
  const portfolios = usePortfolioList()

  const list = portfolios.data ?? []
  const requestedId = searchParams.get('id')
  const active = list.find((p) => String(p.id) === requestedId) ?? list[0]

  const dashboardQuery = usePortfolioDashboard(active?.id ?? undefined)
  const refresh = useRefreshPortfolio(active?.id ?? undefined)

  function selectPortfolio(portfolioId: number) {
    const next = new URLSearchParams(searchParams)
    next.set('id', String(portfolioId))
    setSearchParams(next, { replace: true })
  }

  if (portfolios.isLoading) {
    return (
      <div className={styles.page}>
        <Card>
          <SkeletonCard />
        </Card>
      </div>
    )
  }

  if (portfolios.isError) {
    return (
      <div className={styles.page}>
        <Card>
          <ErrorState message={apiErrorMessage(portfolios.error)} onRetry={() => void portfolios.refetch()} />
        </Card>
      </div>
    )
  }

  if (list.length === 0 || !active) {
    return (
      <div className={styles.page}>
        <Card>
          <EmptyState
            title="No portfolios yet"
            description="Create a portfolio to start tracking allocation and risk."
            action={
              <Button size="sm" onClick={() => setCreateOpen(true)}>
                Create portfolio
              </Button>
            }
          />
        </Card>
        <CreatePortfolioDialog open={createOpen} onClose={() => setCreateOpen(false)} />
      </div>
    )
  }

  const extended = dashboardQuery.data
  const dashboard = extended?.dashboard

  return (
    <div className={styles.page}>
      <PortfolioHeader
        portfolios={list}
        active={active}
        onSelect={selectPortfolio}
        asOf={dashboard?.as_of}
        onRefresh={refresh}
        isRefreshing={dashboardQuery.isFetching}
        onCreateNew={() => setCreateOpen(true)}
        onAddPosition={() => setAddPositionOpen(true)}
        onAddCash={() => setAddCashOpen(true)}
      />
      <CreatePortfolioDialog open={createOpen} onClose={() => setCreateOpen(false)} />
      <AddPositionDialog portfolioId={active.id ?? undefined} open={addPositionOpen} onClose={() => setAddPositionOpen(false)} />
      <AddCashDialog
        portfolioId={active.id ?? undefined}
        baseCurrency={active.base_currency}
        open={addCashOpen}
        onClose={() => setAddCashOpen(false)}
      />

      {dashboardQuery.isLoading ? (
        <Card>
          <SkeletonCard />
        </Card>
      ) : dashboardQuery.isError ? (
        <Card>
          <ErrorState message={apiErrorMessage(dashboardQuery.error)} onRetry={() => void dashboardQuery.refetch()} />
        </Card>
      ) : dashboard ? (
        <>
          <PortfolioSummary dashboard={dashboard} sharpeRatio={extended.sharpe_ratio} currency={active.base_currency} />

          <div className={styles.mainGrid}>
            <div className={styles.mainColumn}>
              <AllocationAnalysis allocation={dashboard.allocation} />
              <PositionBreakdown positions={dashboard.positions} currency={active.base_currency} />
              <div className={styles.twoUp}>
                <PerformanceHistory
                  realizedPnl={dashboard.realized_pnl}
                  unrealizedPnl={dashboard.unrealized_pnl}
                  sharpeRatio={extended.sharpe_ratio}
                  currency={active.base_currency}
                />
                <DrawdownAnalysis risk={dashboard.risk} />
              </div>
              <RecentActivity portfolioId={active.id ?? dashboard.portfolio_id} />
            </div>

            <div className={styles.sideColumn}>
              <CashExposure allocation={dashboard.allocation} cashBalance={dashboard.cash_balance} totalValue={dashboard.total_value} currency={active.base_currency} />
              <Diversification score={dashboard.risk?.diversification_score ?? null} />
              <RiskAnalytics risk={dashboard.risk} recommendations={dashboard.recommendations} />
            </div>
          </div>
        </>
      ) : null}
    </div>
  )
}
