import type { ReactNode, TableHTMLAttributes, ThHTMLAttributes } from 'react'
import clsx from 'clsx'
import styles from './Table.module.css'

export function Table({ children, className, ...rest }: TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className={styles.scroller}>
      <table className={clsx(styles.table, className)} {...rest}>
        {children}
      </table>
    </div>
  )
}

interface TableHeadCellProps extends ThHTMLAttributes<HTMLTableCellElement> {
  children: ReactNode
  align?: 'left' | 'right'
}

/** `onClick` (plus any other <th> prop, e.g. `aria-sort`) is optional -
 * most tables are static; sortable ones (PositionBreakdown) pass it. */
export function TableHeadCell({ children, align = 'left', className, ...rest }: TableHeadCellProps) {
  return (
    <th className={clsx(styles.th, align === 'right' && styles.alignRight, rest.onClick && styles.sortable, className)} {...rest}>
      {children}
    </th>
  )
}

export function TableCell({ children, align = 'left', numeric }: { children: ReactNode; align?: 'left' | 'right'; numeric?: boolean }) {
  return <td className={clsx(styles.td, align === 'right' && styles.alignRight, numeric && 'num')}>{children}</td>
}
