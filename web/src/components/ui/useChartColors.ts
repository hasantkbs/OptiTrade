import { useEffect, useState } from 'react'

export interface ChartColors {
  accent: string
  positive: string
  negative: string
  warning: string
  info: string
  border: string
  textSecondary: string
}

function readColors(): ChartColors {
  const styles = getComputedStyle(document.documentElement)
  const get = (name: string) => styles.getPropertyValue(name).trim()
  return {
    accent: get('--color-accent'),
    positive: get('--color-positive'),
    negative: get('--color-negative'),
    warning: get('--color-warning'),
    info: get('--color-info'),
    border: get('--color-border'),
    textSecondary: get('--color-text-secondary'),
  }
}

/**
 * Recharts needs literal color values, not CSS custom properties (SVG
 * presentation attributes don't resolve var() reliably) - this reads
 * the resolved theme tokens and re-reads them whenever the theme
 * attribute or system color-scheme changes, so charts stay correct
 * across a live theme switch (see ThemeContext).
 */
export function useChartColors(): ChartColors {
  const [colors, setColors] = useState<ChartColors>(() =>
    typeof window === 'undefined' ? ({} as ChartColors) : readColors(),
  )

  useEffect(() => {
    const update = () => setColors(readColors())
    update()

    const observer = new MutationObserver(update)
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })

    const media = window.matchMedia('(prefers-color-scheme: dark)')
    media.addEventListener('change', update)

    return () => {
      observer.disconnect()
      media.removeEventListener('change', update)
    }
  }, [])

  return colors
}
