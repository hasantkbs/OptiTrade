import { Link } from 'react-router-dom'
import { Button } from '../../components/ui/Button'
import { Dropdown } from '../../components/ui/Dropdown'
import type { Portfolio } from '../../api/types'
import styles from './PortfolioHeader.module.css'

interface PortfolioHeaderProps {
  portfolios: Portfolio[]
  active: Portfolio
  onSelect: (portfolioId: number) => void
  asOf?: string
  onRefresh: () => void
  isRefreshing?: boolean
  onCreateNew: () => void
  onAddPosition: () => void
  onAddCash: () => void
}

export function PortfolioHeader({
  portfolios,
  active,
  onSelect,
  asOf,
  onRefresh,
  isRefreshing,
  onCreateNew,
  onAddPosition,
  onAddCash,
}: PortfolioHeaderProps) {
  return (
    <div className={styles.header}>
      <div>
        <Link to="/" className={styles.backLink}>
          ← Dashboard
        </Link>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>{active.name}</h1>
          {portfolios.length > 1 ? (
            <Dropdown
              trigger={<span className={styles.selectorTrigger}>Switch portfolio ▾</span>}
              items={portfolios.map((portfolio) => ({
                label: portfolio.name,
                onSelect: () => {
                  if (portfolio.id != null) onSelect(portfolio.id)
                },
              }))}
            />
          ) : null}
        </div>
        <p className={styles.subtitle}>
          {active.base_currency} · Created {new Date(active.created_at).toLocaleDateString()}
          {asOf ? ` · As of ${new Date(asOf).toLocaleString()}` : ''}
        </p>
      </div>
      <div className={styles.actions}>
        <Button size="sm" onClick={onAddPosition}>
          + Add position
        </Button>
        <Button variant="secondary" size="sm" onClick={onAddCash}>
          + Add cash
        </Button>
        <Button variant="secondary" size="sm" onClick={onCreateNew}>
          New portfolio
        </Button>
        <Button variant="secondary" size="sm" onClick={onRefresh} isLoading={isRefreshing}>
          Refresh
        </Button>
      </div>
    </div>
  )
}
