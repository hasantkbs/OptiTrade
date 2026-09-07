import { KpiCardsSection } from '../features/dashboard/sections/KpiCardsSection'
import { EngineScoreSection } from '../features/dashboard/sections/EngineScoreSection'
import { DecisionDistributionSection } from '../features/dashboard/sections/DecisionDistributionSection'
import { PortfolioSummarySection } from '../features/dashboard/sections/PortfolioSummarySection'
import { WatchlistSummarySection } from '../features/dashboard/sections/WatchlistSummarySection'
import { RecentAlertsSection } from '../features/dashboard/sections/RecentAlertsSection'
import { RecentDecisionsSection } from '../features/dashboard/sections/RecentDecisionsSection'
import styles from './DashboardPage.module.css'

export function DashboardPage() {
  return (
    <div className={styles.page}>
      <KpiCardsSection />

      <div className={styles.mainGrid}>
        <div className={styles.mainColumn}>
          <EngineScoreSection />
          <div className={styles.twoUp}>
            <PortfolioSummarySection />
            <DecisionDistributionSection />
          </div>
          <RecentDecisionsSection />
        </div>

        <div className={styles.sideColumn}>
          <WatchlistSummarySection />
          <RecentAlertsSection />
        </div>
      </div>
    </div>
  )
}
