import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { ThemeProvider, useTheme } from './ThemeContext'

function Probe() {
  const { preference, setPreference } = useTheme()
  return (
    <div>
      <span data-testid="preference">{preference}</span>
      <button onClick={() => setPreference('dark')}>dark</button>
      <button onClick={() => setPreference('light')}>light</button>
      <button onClick={() => setPreference('system')}>system</button>
    </div>
  )
}

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

describe('ThemeProvider', () => {
  it('defaults to system preference with no explicit data-theme attribute', () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    expect(screen.getByTestId('preference')).toHaveTextContent('system')
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
  })

  it('switches to dark and applies data-theme="dark"', async () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    await userEvent.click(screen.getByText('dark'))
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(localStorage.getItem('optitrade.theme')).toBe('dark')
  })

  it('switches to light and applies data-theme="light"', async () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    await userEvent.click(screen.getByText('light'))
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('persists the preference across a remount (localStorage)', () => {
    localStorage.setItem('optitrade.theme', 'dark')
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    expect(screen.getByTestId('preference')).toHaveTextContent('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('returning to system removes the explicit data-theme attribute', async () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    await userEvent.click(screen.getByText('dark'))
    await userEvent.click(screen.getByText('system'))
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
  })
})
