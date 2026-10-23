import type { MetricDef } from './types'

const compact = new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 })

export function formatNumber(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '–'
  return value.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined) return '–'
  return Math.abs(value) >= 1000 ? compact.format(value) : formatNumber(value, Math.abs(value) < 10 && value % 1 ? 1 : 0)
}

export function formatMetric(metric: MetricDef | undefined, value: number | null | undefined, withUnit = true): string {
  if (!metric) return formatNumber(value)
  const text = formatNumber(value, metric.decimals)
  if (text === '–' || !withUnit || !metric.unit) return text
  return metric.unit === '%' ? `${text}%` : `${text} ${metric.unit}`
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '–'
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  if (h === 0) return `${m} min`
  return `${h}h ${m.toString().padStart(2, '0')}m`
}

export function formatPace(speedMps: number | null | undefined): string {
  if (!speedMps) return '–'
  const secPerKm = 1000 / speedMps
  const min = Math.floor(secPerKm / 60)
  const sec = Math.round(secPerKm % 60)
  return `${min}:${sec.toString().padStart(2, '0')} /km`
}

export function formatSpeed(speedMps: number | null | undefined): string {
  if (!speedMps) return '–'
  return `${(speedMps * 3.6).toFixed(1)} km/h`
}

export function formatDistance(meters: number | null | undefined): string {
  if (!meters) return '–'
  return meters >= 1000 ? `${(meters / 1000).toFixed(2)} km` : `${Math.round(meters)} m`
}

const dayFormat = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short' })
const longDayFormat = new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
const monthFormat = new Intl.DateTimeFormat(undefined, { month: 'short', year: '2-digit' })

/** Parse YYYY-MM-DD as a local calendar date (not UTC midnight). */
export function parseDay(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function toIsoDay(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export function addDays(iso: string, days: number): string {
  const date = parseDay(iso)
  date.setDate(date.getDate() + days)
  return toIsoDay(date)
}

export function formatDay(iso: string, bucket: 'day' | 'week' | 'month' = 'day'): string {
  const date = parseDay(iso)
  if (bucket === 'month') return monthFormat.format(date)
  return dayFormat.format(date)
}

export function formatLongDay(iso: string): string {
  return longDayFormat.format(parseDay(iso))
}

export function formatRelative(isoTimestamp: string | null | undefined): string {
  if (!isoTimestamp) return 'never'
  const diff = Date.now() - new Date(isoTimestamp).getTime()
  const minutes = Math.round(diff / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  return `${Math.round(hours / 24)} d ago`
}

export const SPORT_LABELS: Record<string, string> = {
  run: 'Run',
  ride: 'Ride',
  swim: 'Swim',
  walk: 'Walk / hike',
  team: 'Court & team',
  strength: 'Gym & classes',
  other: 'Other',
}
