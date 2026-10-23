import { useMemo } from 'react'
import { formatNumber } from './format'
import { useAuthState } from './hooks'
import type { MetricDef, Preferences } from './types'

export const DEFAULT_PREFS: Preferences = {
  distance: 'km',
  weight: 'kg',
  volume: 'ml',
  elevation: 'm',
  week_start: 'monday',
  time_format: '24h',
}

const KM_PER_MI = 1.609344
const LB_PER_KG = 2.2046226218
const ML_PER_FLOZ = 29.5735295625
const FT_PER_M = 3.280839895

export type Quantity = 'distance_km' | 'mass_kg' | 'volume_ml'

/** Stored values are metric; convert to the viewer's unit. All conversions are pure scaling,
 * so percentage changes and indexed series are unaffected. */
export function convert(quantity: Quantity | null | undefined, value: number, prefs: Preferences): number {
  switch (quantity) {
    case 'distance_km':
      return prefs.distance === 'mi' ? value / KM_PER_MI : value
    case 'mass_kg':
      return prefs.weight === 'lb' ? value * LB_PER_KG : prefs.weight === 'st' ? (value * LB_PER_KG) / 14 : value
    case 'volume_ml':
      return prefs.volume === 'floz' ? value / ML_PER_FLOZ : value
    default:
      return value
  }
}

function unitLabel(quantity: Quantity | null | undefined, prefs: Preferences, fallback: string): string {
  switch (quantity) {
    case 'distance_km':
      return prefs.distance
    case 'mass_kg':
      return prefs.weight
    case 'volume_ml':
      return prefs.volume === 'floz' ? 'fl oz' : 'ml'
    default:
      return fallback
  }
}

export interface DisplayMetric {
  def: MetricDef
  toDisplay: (v: number) => number
  /** Text with unit, e.g. "11 st 6 lb", "72.4 kg", "5.3 mi". */
  format: (v: number | null | undefined) => string
}

function stoneText(stones: number): string {
  let st = Math.floor(stones)
  let lb = Math.round((stones - st) * 14)
  if (lb === 14) {
    st += 1
    lb = 0
  }
  return `${st} st ${lb} lb`
}

export function displayMetric(metric: MetricDef, prefs: Preferences): DisplayMetric {
  const quantity = metric.quantity as Quantity | null
  const unit = unitLabel(quantity, prefs, metric.unit)
  const decimals = quantity === 'volume_ml' && prefs.volume === 'floz' ? 0 : metric.decimals
  const def: MetricDef = { ...metric, unit, decimals }
  const toDisplay = (v: number) => convert(quantity, v, prefs)
  const format = (v: number | null | undefined) => {
    if (v === null || v === undefined) return '–'
    if (quantity === 'mass_kg' && prefs.weight === 'st') return stoneText(v)
    const text = formatNumber(v, decimals)
    if (!unit) return text
    return unit === '%' ? `${text}%` : `${text} ${unit}`
  }
  return { def, toDisplay, format }
}

/** The signed-in viewer's effective preferences. */
export function usePrefs(): Preferences {
  const { data } = useAuthState()
  return data?.me?.preferences ?? DEFAULT_PREFS
}

/** Formatters bound to the viewer's units. Inputs are always metric (m, m/s, kg, ml). */
export function useUnits() {
  const prefs = usePrefs()
  return useMemo(() => {
    const miles = prefs.distance === 'mi'
    const feet = prefs.elevation === 'ft'
    const clock = new Intl.DateTimeFormat(undefined, {
      hour: 'numeric',
      minute: '2-digit',
      hour12: prefs.time_format === '12h',
    })
    return {
      prefs,
      metric: (m: MetricDef) => displayMetric(m, prefs),
      distanceUnit: miles ? 'mi' : 'km',
      /** metres → "6.31 km" / "3.92 mi" (short distances in m / yd stay readable). */
      distance(meters: number | null | undefined): string {
        if (!meters) return '–'
        if (miles) return meters < 400 ? `${Math.round(meters * 1.0936)} yd` : `${(meters / 1609.344).toFixed(2)} mi`
        return meters >= 1000 ? `${(meters / 1000).toFixed(2)} km` : `${Math.round(meters)} m`
      },
      /** metres → number in km or mi (for charts / totals). */
      distanceValue: (meters: number) => (miles ? meters / 1609.344 : meters / 1000),
      kmToDisplay: (km: number) => (miles ? km / KM_PER_MI : km),
      pace(speedMps: number | null | undefined): string {
        if (!speedMps) return '–'
        const secPer = (miles ? 1609.344 : 1000) / speedMps
        const min = Math.floor(secPer / 60)
        const sec = Math.round(secPer % 60)
        return `${min}:${String(sec === 60 ? 0 : sec).padStart(2, '0')} /${miles ? 'mi' : 'km'}`
      },
      /** m/s → minutes per km or mi, as a number for charts. */
      paceValue: (speedMps: number) => (miles ? 1609.344 : 1000) / speedMps / 60,
      speed(speedMps: number | null | undefined): string {
        if (!speedMps) return '–'
        return miles ? `${(speedMps * 2.236936).toFixed(1)} mph` : `${(speedMps * 3.6).toFixed(1)} km/h`
      },
      speedValue: (speedMps: number) => (miles ? speedMps * 2.236936 : speedMps * 3.6),
      speedUnit: miles ? 'mph' : 'km/h',
      paceUnit: miles ? 'min/mi' : 'min/km',
      elevation(meters: number | null | undefined): string {
        if (meters === null || meters === undefined) return '–'
        return feet ? `${Math.round(meters * FT_PER_M)} ft` : `${Math.round(meters)} m`
      },
      elevationValue: (meters: number) => (feet ? meters * FT_PER_M : meters),
      elevationUnit: feet ? 'ft' : 'm',
      /** Date → "22:45" or "10:45 pm". */
      clock: (date: Date) => clock.format(date),
      /** Minutes since midnight → axis label. */
      timeOfDay(minutes: number | string): string {
        const m = Number(minutes)
        const d = new Date(2000, 0, 1, Math.floor(m / 60) % 24, m % 60)
        return prefs.time_format === '12h'
          ? d.toLocaleTimeString(undefined, { hour: 'numeric', hour12: true })
          : `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
      },
    }
  }, [prefs])
}

export type Units = ReturnType<typeof useUnits>
