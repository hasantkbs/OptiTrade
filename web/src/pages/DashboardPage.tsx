import { DashboardKpis } from '../features/dashboard/sections/DashboardKpis'
import { PortfolioPerformance } from '../features/dashboard/sections/PortfolioPerformance'
import { EngineIntelligence } from '../features/dashboard/sections/EngineIntelligence'
import { MarketOverview } from '../features/dashboard/sections/MarketOverview'
import { RecentDecisions } from '../features/dashboard/sections/RecentDecisions'
import { LearningOverview } from '../features/dashboard/sections/LearningOverview'
import { WatchlistIntelligence } from '../features/dashboard/sections/WatchlistIntelligence'
import { AlertsOverview } from '../features/dashboard/sections/AlertsOverview'
import styles from './DashboardPage.module.css'

export function DashboardPage() {
  return (
    <div className={styles.page}>
      <DashboardKpis />

      <div className={styles.mainGrid}>
        <div className={styles.mainColumn}>
          <PortfolioPerformance />
          <EngineIntelligence />
          <div className={styles.twoUp}>
            <MarketOverview />
            <RecentDecisions />
          </div>
          <LearningOverview />
        </div>

        <div className={styles.sideColumn}>
          <WatchlistIntelligence />
          <AlertsOverview />
        </div>
      </div>
    </div>
  )
}
