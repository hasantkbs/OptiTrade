import { useState, type FormEvent } from 'react'
import clsx from 'clsx'
import { Button } from '../../components/ui/Button'
import { Card, CardHeader, CardSubtitle, CardTitle } from '../../components/ui/Card'
import { Input } from '../../components/ui/Input'
import { useWatchlistItems, useWatchlists } from '../dashboard/hooks'
import styles from './SymbolPicker.module.css'

interface SymbolPickerProps {
  activeSymbol: string | null
  isAnalyzing: boolean
  onAnalyze: (symbol: string) => void
}

/**
 * The single entry point into decision analysis on this page - reuses
 * `useWatchlists`/`useWatchlistItems` (features/dashboard/hooks.ts, the
 * same hooks the Dashboard and Watchlist page already use) for the
 * quick-pick chips rather than a second watchlist fetch. Only ever
 * analyzes one symbol at a time, on explicit user action (typed submit
 * or a chip click) - never a bulk scan across a whole watchlist
 * (WEB STEP 5 §14), and every control disables while an analysis is
 * already in flight (WEB STEP 5 §3, §20 - prevents duplicate
 * /quant/analyze submissions and respects its 10/minute rate limit).
 */
export function SymbolPicker({ activeSymbol, isAnalyzing, onAnalyze }: SymbolPickerProps) {
  const [input, setInput] = useState('')
  const watchlists = useWatchlists()
  const firstWatchlist = watchlists.data?.[0]
  const items = useWatchlistItems(firstWatchlist?.id ?? undefined)

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = input.trim()
    if (trimmed && !isAnalyzing) {
      onAnalyze(trimmed)
    }
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Analyze a symbol</CardTitle>
          <CardSubtitle>Runs the live Decision Engine pipeline for one symbol at a time</CardSubtitle>
        </div>
      </CardHeader>

      <form onSubmit={handleSubmit} className={styles.form}>
        <Input
          label="Symbol"
          value={input}
          onChange={(event) => setInput(event.target.value.toUpperCase())}
          placeholder="e.g. AAPL"
          disabled={isAnalyzing}
          autoComplete="off"
        />
        <Button type="submit" disabled={isAnalyzing || !input.trim()} isLoading={isAnalyzing}>
          Analyze
        </Button>
      </form>

      {items.data && items.data.length > 0 ? (
        <div className={styles.quickPick}>
          <span className={styles.quickPickLabel}>From your watchlist</span>
          <div className={styles.chips}>
            {items.data.map((item) => (
              <button
                key={item.id}
                type="button"
                className={clsx(styles.chip, item.symbol === activeSymbol && styles.chipActive)}
                onClick={() => onAnalyze(item.symbol)}
                disabled={isAnalyzing}
              >
                {item.symbol}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </Card>
  )
}
