import { Link } from 'react-router-dom'
import { Button } from '../../components/ui/Button'
import styles from './LearningHeader.module.css'

interface LearningHeaderProps {
  onRefresh: () => void
  isRefreshing: boolean
}

export function LearningHeader({ onRefresh, isRefreshing }: LearningHeaderProps) {
  return (
    <div className={styles.header}>
      <div>
        <h1 className={styles.title}>Continuous Learning</h1>
        <p className={styles.subtitle}>
          How the Technical, Fundamental and News engines are performing, how their weights and calibration are
          changing, and what the learning system currently recommends.
        </p>
      </div>
      <div className={styles.actions}>
        <Link to="/decisions" className={styles.decisionLink}>
          Analyze a symbol →
        </Link>
        <Button variant="secondary" size="sm" onClick={onRefresh} isLoading={isRefreshing}>
          Refresh
        </Button>
      </div>
    </div>
  )
}
