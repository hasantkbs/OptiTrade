import { useMemo, useState } from 'react'
import { Input } from '../../components/ui/Input'
import { Badge } from '../../components/ui/Badge'
import { useMarketSymbols } from './hooks'
import styles from './SymbolSearch.module.css'

interface SymbolSearchProps {
  onSelect: (symbol: string) => void
  label?: string
  placeholder?: string
}

const MAX_RESULTS = 8

/**
 * Type-ahead over useMarketSymbols' merged TR/US/CRYPTO list. Every
 * result comes from the backend's own canonical symbol list, so a
 * BIST pick always carries its required ".IS" suffix - picking a
 * result here (rather than hand-typing a symbol) is what keeps the
 * backend's market auto-detection (core/market_config.py::
 * get_market_for_symbol) correct for news/analysis downstream.
 */
export function SymbolSearch({ onSelect, label = 'Search stocks or crypto', placeholder }: SymbolSearchProps) {
  const [query, setQuery] = useState('')
  const symbols = useMarketSymbols()

  const matches = useMemo(() => {
    const trimmed = query.trim().toUpperCase()
    if (!trimmed || !symbols.data) return []
    return symbols.data
      .filter((s) => s.symbol.toUpperCase().includes(trimmed) || s.name.toUpperCase().includes(trimmed))
      .slice(0, MAX_RESULTS)
  }, [query, symbols.data])

  function handleSelect(symbol: string) {
    onSelect(symbol)
    setQuery('')
  }

  return (
    <div className={styles.wrapper}>
      <Input
        label={label}
        placeholder={placeholder ?? 'e.g. AAPL, Garanti, Bitcoin'}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      {symbols.isError ? <p className={styles.error}>Couldn&apos;t load the symbol list.</p> : null}
      {matches.length > 0 ? (
        <ul className={styles.results}>
          {matches.map((match) => (
            <li key={match.symbol}>
              <button type="button" className={styles.resultButton} onClick={() => handleSelect(match.symbol)}>
                <span className={styles.resultSymbol}>{match.symbol}</span>
                <span className={styles.resultName}>{match.name}</span>
                <Badge>{match.market}</Badge>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {query.trim() && !symbols.isLoading && matches.length === 0 ? (
        <p className={styles.empty}>No matching symbol.</p>
      ) : null}
    </div>
  )
}
