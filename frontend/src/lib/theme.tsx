import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type ThemeChoice = 'system' | 'light' | 'dark'
type Resolved = 'light' | 'dark'

/**
 * Categorical person colours, in fixed order. Validated (CVD + contrast) for both modes;
 * the dark column is the same hues stepped for the dark surface, not a flip.
 */
const SERIES_LIGHT = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']
const SERIES_DARK = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767']

/** One-hue ordinal ramp (blue 250 → 650) for ordered classes such as HR zones. */
const RAMP_LIGHT = ['#86b6ef', '#5598e7', '#2a78d6', '#1c5cab', '#104281']
const RAMP_DARK = ['#184f95', '#1c5cab', '#2a78d6', '#5598e7', '#86b6ef']

const CHROME = {
  light: { surface: '#fcfcfb', grid: '#e1e0d9', axis: '#c3c2b7', muted: '#898781', ink: '#0b0b0b', ink2: '#52514e', deemph: '#c3c2b7', neutral: '#d9d8d1' },
  dark: { surface: '#1a1a19', grid: '#2c2c2a', axis: '#383835', muted: '#898781', ink: '#f0efec', ink2: '#c3c2b7', deemph: '#4a4a46', neutral: '#4a4a46' },
}

export interface Palette {
  mode: Resolved
  series: (slot: number) => string
  ramp: string[]
  chrome: (typeof CHROME)['light']
}

interface ThemeState {
  choice: ThemeChoice
  setChoice: (c: ThemeChoice) => void
  palette: Palette
}

const ThemeContext = createContext<ThemeState | null>(null)

function readStoredChoice(): ThemeChoice {
  try {
    const value = localStorage.getItem('gd-theme')
    if (value === 'light' || value === 'dark' || value === 'system') return value
  } catch {
    /* storage unavailable (private mode) - fall back to the OS setting */
  }
  return 'system'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoiceState] = useState<ThemeChoice>(readStoredChoice)
  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false,
  )

  useEffect(() => {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!media) return
    const listener = (e: MediaQueryListEvent) => setSystemDark(e.matches)
    media.addEventListener('change', listener)
    return () => media.removeEventListener('change', listener)
  }, [])

  const mode: Resolved = choice === 'system' ? (systemDark ? 'dark' : 'light') : choice

  useEffect(() => {
    document.documentElement.dataset.theme = mode
  }, [mode])

  const value = useMemo<ThemeState>(() => {
    const series = mode === 'dark' ? SERIES_DARK : SERIES_LIGHT
    return {
      choice,
      setChoice: (c) => {
        setChoiceState(c)
        try {
          localStorage.setItem('gd-theme', c)
        } catch {
          /* ignore */
        }
      },
      palette: {
        mode,
        series: (slot) => series[((slot % series.length) + series.length) % series.length],
        ramp: mode === 'dark' ? RAMP_DARK : RAMP_LIGHT,
        chrome: CHROME[mode],
      },
    }
  }, [choice, mode])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeState {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme outside ThemeProvider')
  return ctx
}

export function usePalette(): Palette {
  return useTheme().palette
}
