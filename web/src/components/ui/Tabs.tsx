import { useId, type ReactNode } from 'react'
import clsx from 'clsx'
import styles from './Tabs.module.css'

export interface TabItem {
  id: string
  label: string
  content: ReactNode
}

export function Tabs({ items, active, onChange }: { items: TabItem[]; active: string; onChange: (id: string) => void }) {
  const baseId = useId()
  const activeItem = items.find((item) => item.id === active) ?? items[0]

  return (
    <div>
      <div role="tablist" className={styles.list}>
        {items.map((item) => {
          const selected = item.id === activeItem?.id
          return (
            <button
              key={item.id}
              role="tab"
              id={`${baseId}-tab-${item.id}`}
              aria-controls={`${baseId}-panel-${item.id}`}
              aria-selected={selected}
              tabIndex={selected ? 0 : -1}
              className={clsx(styles.tab, selected && styles.active)}
              onClick={() => onChange(item.id)}
            >
              {item.label}
            </button>
          )
        })}
      </div>
      {activeItem ? (
        <div role="tabpanel" id={`${baseId}-panel-${activeItem.id}`} aria-labelledby={`${baseId}-tab-${activeItem.id}`}>
          {activeItem.content}
        </div>
      ) : null}
    </div>
  )
}
