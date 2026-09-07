import type { ReactNode, TableHTMLAttributes } from 'react'
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

export function TableHeadCell({ children, align = 'left' }: { children: ReactNode; align?: 'left' | 'right' }) {
  return <th className={clsx(styles.th, align === 'right' && styles.alignRight)}>{children}</th>
}

export function TableCell({ children, align = 'left', numeric }: { children: ReactNode; align?: 'left' | 'right'; numeric?: boolean }) {
  return <td className={clsx(styles.td, align === 'right' && styles.alignRight, numeric && 'num')}>{children}</td>
}
