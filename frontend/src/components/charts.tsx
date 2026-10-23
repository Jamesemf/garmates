import { useState, type ReactNode } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatCompact, formatDay, formatMetric, formatNumber } from '../lib/format'
import { usePalette } from '../lib/theme'
import type { Bucket, MetricDef, Person, Point, SeriesResponse } from '../lib/types'
import { cx, EmptyState } from './ui'

export type Row = { date: string } & Record<string, number | null | string>

export const personKey = (person: Pick<Person, 'id'>) => `p${person.id}`

/** Turn a /api/series response into chart rows: one row per date, one column per person. */
export function mergeSeries(
  response: SeriesResponse | undefined,
  people: Person[],
  metric: string,
  transform?: (value: number, person: Person) => number | null,
): Row[] {
  if (!response) return []
  const rows = new Map<string, Row>()
  for (const person of people) {
    const points: Point[] = response.people[String(person.id)]?.points ?? []
    for (const point of points) {
      const raw = point[metric]
      if (raw === null || raw === undefined || typeof raw !== 'number') continue
      const row = rows.get(point.date) ?? { date: point.date }
      row[personKey(person)] = transform ? transform(raw, person) : raw
      rows.set(point.date, row)
    }
  }
  return [...rows.values()].sort((a, b) => a.date.localeCompare(b.date))
}

export function lastValue(rows: Row[], person: Person): number | null {
  for (let i = rows.length - 1; i >= 0; i--) {
    const value = rows[i][personKey(person)]
    if (typeof value === 'number') return value
  }
  return null
}

// --- container -----------------------------------------------------------------------------

export function ChartCard({
  title,
  subtitle,
  legend,
  children,
  table,
  loading,
  empty,
  className,
}: {
  title: string
  subtitle?: ReactNode
  legend?: ReactNode
  children: ReactNode
  table?: ReactNode
  loading?: boolean
  empty?: boolean
  className?: string
}) {
  const [showTable, setShowTable] = useState(false)
  return (
    <figure className={cx('min-w-0 rounded-xl border border-line bg-surface p-4 sm:p-5', className)}>
      <figcaption className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-ink-2">{subtitle}</p>}
        </div>
        {table && !empty && (
          <button
            type="button"
            onClick={() => setShowTable((v) => !v)}
            className="rounded-md px-2 py-0.5 text-xs font-medium text-ink-2 hover:bg-wash hover:text-ink"
            aria-pressed={showTable}
          >
            {showTable ? 'Chart' : 'Table'}
          </button>
        )}
      </figcaption>
      {legend && !empty && <div className="mb-2">{legend}</div>}
      <div className={cx('transition-opacity', loading && 'opacity-50')}>
        {empty ? (
          <EmptyState title="No data for this period yet" />
        ) : showTable && table ? (
          table
        ) : (
          children
        )}
      </div>
    </figure>
  )
}

export function DataTable({
  columns,
  rows,
}: {
  columns: { key: string; label: ReactNode; format?: (v: unknown) => string }[]
  rows: Record<string, unknown>[]
}) {
  return (
    <div className="max-h-80 overflow-auto rounded-lg border border-line">
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-raised text-ink-2">
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className="px-3 py-2 font-medium">
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular">
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-line">
              {columns.map((c) => (
                <td key={c.key} className="px-3 py-1.5 text-ink">
                  {c.format ? c.format(row[c.key]) : String(row[c.key] ?? '–')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Table twin for a per-person chart. */
export function PeopleTable({
  rows,
  people,
  bucket,
  format,
}: {
  rows: Row[]
  people: Person[]
  bucket: Bucket
  format: (v: number | null) => string
}) {
  return (
    <DataTable
      columns={[
        { key: 'date', label: 'Date', format: (v) => formatDay(String(v), bucket) },
        ...people.map((p) => ({
          key: personKey(p),
          label: p.name,
          format: (v: unknown) => format(typeof v === 'number' ? v : null),
        })),
      ]}
      rows={[...rows].reverse()}
    />
  )
}

// --- legend & tooltip ----------------------------------------------------------------------

export function PeopleLegend({
  people,
  values,
  shape = 'line',
}: {
  people: Person[]
  values?: Record<number, string>
  shape?: 'line' | 'rect'
}) {
  const palette = usePalette()
  if (people.length < 2 && !values) return null
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
      {people.map((p) => (
        <li key={p.id} className="flex items-center gap-1.5 text-ink-2">
          <span
            aria-hidden
            className={shape === 'line' ? 'inline-block h-0.5 w-3 rounded' : 'inline-block h-2.5 w-2.5 rounded-sm'}
            style={{ background: palette.series(p.color_slot) }}
          />
          <span>{p.name}</span>
          {values?.[p.id] && <span className="font-semibold text-ink">{values[p.id]}</span>}
        </li>
      ))}
    </ul>
  )
}

interface TooltipEntry {
  dataKey?: string | number
  value?: number | string | null
  color?: string
}

function ChartTooltip({
  active,
  payload,
  label,
  people,
  format,
  labelFormat,
  colorFor,
}: {
  active?: boolean
  payload?: TooltipEntry[]
  label?: string | number
  people: Person[]
  format: (v: number | null) => string
  labelFormat: (label: string) => string
  colorFor?: (p: Person) => string
}) {
  const palette = usePalette()
  const color = colorFor ?? ((p: Person) => palette.series(p.color_slot))
  if (!active || !payload?.length || label === undefined) return null
  const byKey = new Map(payload.map((entry) => [String(entry.dataKey), entry.value]))
  return (
    <div className="rounded-lg border border-line bg-raised px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 text-ink-2">{labelFormat(String(label))}</p>
      <ul className="space-y-0.5">
        {people.map((p) => {
          const value = byKey.get(personKey(p))
          return (
            <li key={p.id} className="flex items-center gap-2">
              <span aria-hidden className="inline-block h-0.5 w-3 rounded" style={{ background: color(p) }} />
              <span className="font-semibold text-ink tabular">
                {format(typeof value === 'number' ? value : null)}
              </span>
              <span className="text-ink-2">{p.name}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

// --- line chart ----------------------------------------------------------------------------

export function PeopleLineChart({
  rows,
  people,
  metric,
  bucket = 'day',
  height = 220,
  connectNulls = false,
  referenceY,
  format,
  yDomain,
  xFormat,
  xTicks,
  colorFor,
}: {
  rows: Row[]
  people: Person[]
  metric?: MetricDef
  bucket?: Bucket
  height?: number
  connectNulls?: boolean
  referenceY?: number
  format?: (v: number | null) => string
  yDomain?: [number | string | ((v: number) => number), number | string | ((v: number) => number)]
  xFormat?: (v: string) => string
  /** Explicit x tick values (must exist in the data), e.g. round hours. */
  xTicks?: string[]
  /** Override series colours (default: each person's palette slot). */
  colorFor?: (p: Person) => string
}) {
  const palette = usePalette()
  const seriesColor = colorFor ?? ((p: Person) => palette.series(p.color_slot))
  const valueFormat = format ?? ((v: number | null) => formatMetric(metric, v))
  const tickFormat = xFormat ?? ((v: string) => formatDay(v, bucket))
  const lastIndex: Record<string, number> = {}
  for (const p of people) {
    const key = personKey(p)
    for (let i = rows.length - 1; i >= 0; i--) {
      if (typeof rows[i][key] === 'number') {
        lastIndex[key] = i
        break
      }
    }
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} stroke={palette.chrome.grid} strokeWidth={1} />
        <XAxis
          dataKey="date"
          tickFormatter={tickFormat}
          tickLine={false}
          axisLine={{ stroke: palette.chrome.axis }}
          minTickGap={28}
          tickMargin={6}
          ticks={xTicks}
          interval={xTicks ? 0 : 'preserveEnd'}
        />
        <YAxis
          width={44}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: number) => formatCompact(v)}
          domain={yDomain ?? ['auto', 'auto']}
          allowDecimals={false}
        />
        {referenceY !== undefined && (
          <ReferenceLine y={referenceY} stroke={palette.chrome.axis} strokeWidth={1} />
        )}
        <Tooltip
          cursor={{ stroke: palette.chrome.axis, strokeWidth: 1 }}
          content={<ChartTooltip people={people} format={valueFormat} labelFormat={tickFormat} colorFor={seriesColor} />}
          isAnimationActive={false}
        />
        {people.map((p) => {
          const key = personKey(p)
          const color = seriesColor(p)
          return (
            <Line
              key={p.id}
              dataKey={key}
              name={p.name}
              type="monotone"
              stroke={color}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              connectNulls={connectNulls}
              isAnimationActive={false}
              activeDot={{ r: 4, fill: color, stroke: palette.chrome.surface, strokeWidth: 2 }}
              dot={(props: { index?: number; cx?: number; cy?: number }) =>
                props.index === lastIndex[key] && props.cx !== undefined && props.cy !== undefined ? (
                  <circle key={`end-${key}`} cx={props.cx} cy={props.cy} r={4} fill={color} stroke={palette.chrome.surface} strokeWidth={2} />
                ) : (
                  <g key={`d-${key}-${props.index}`} />
                )
              }
            />
          )
        })}
      </LineChart>
    </ResponsiveContainer>
  )
}

// --- bar chart -----------------------------------------------------------------------------

export function PeopleBarChart({
  rows,
  people,
  metric,
  bucket = 'week',
  height = 220,
  format,
  referenceY,
}: {
  rows: Row[]
  people: Person[]
  metric?: MetricDef
  bucket?: Bucket
  height?: number
  format?: (v: number | null) => string
  referenceY?: number
}) {
  const palette = usePalette()
  const valueFormat = format ?? ((v: number | null) => formatMetric(metric, v))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }} barGap={2} barCategoryGap="22%">
        <CartesianGrid vertical={false} stroke={palette.chrome.grid} strokeWidth={1} />
        <XAxis
          dataKey="date"
          tickFormatter={(v: string) => formatDay(v, bucket)}
          tickLine={false}
          axisLine={{ stroke: palette.chrome.axis }}
          minTickGap={20}
          tickMargin={6}
        />
        <YAxis width={44} tickLine={false} axisLine={false} tickFormatter={(v: number) => formatCompact(v)} />
        {referenceY !== undefined && <ReferenceLine y={referenceY} stroke={palette.chrome.axis} />}
        <Tooltip
          cursor={{ fill: palette.mode === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(11,11,11,0.04)' }}
          content={
            <ChartTooltip people={people} format={valueFormat} labelFormat={(v) => (bucket === 'week' ? `Week of ${formatDay(v)}` : formatDay(v, bucket))} />
          }
          isAnimationActive={false}
        />
        {people.map((p) => (
          <Bar
            key={p.id}
            dataKey={personKey(p)}
            name={p.name}
            fill={palette.series(p.color_slot)}
            radius={[4, 4, 0, 0]}
            maxBarSize={24}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}

// --- sparkline -----------------------------------------------------------------------------

/** Tiny trend line: earlier days in the de-emphasis grey, the current period in the accent. */
export function Sparkline({
  values,
  highlightFrom,
  color,
  width = 96,
  height = 28,
}: {
  values: (number | null)[]
  highlightFrom: number
  color: string
  width?: number
  height?: number
}) {
  const palette = usePalette()
  const numbers = values.filter((v): v is number => v !== null)
  if (numbers.length < 2) return <svg width={width} height={height} aria-hidden />
  const min = Math.min(...numbers)
  const max = Math.max(...numbers)
  const span = max - min || 1
  const step = width / Math.max(1, values.length - 1)
  const point = (v: number, i: number) => `${(i * step).toFixed(1)},${(height - 3 - ((v - min) / span) * (height - 6)).toFixed(1)}`
  const segments = (from: number, to: number) => {
    const parts: string[] = []
    let current: string[] = []
    for (let i = from; i < to; i++) {
      const v = values[i]
      if (v === null) {
        if (current.length > 1) parts.push(current.join(' '))
        current = []
      } else current.push(point(v, i))
    }
    if (current.length > 1) parts.push(current.join(' '))
    return parts
  }
  const split = Math.max(0, Math.min(values.length, highlightFrom))
  return (
    <svg width={width} height={height} aria-hidden className="overflow-visible">
      {segments(0, Math.min(values.length, split + 1)).map((pts, i) => (
        <polyline key={`b${i}`} points={pts} fill="none" stroke={palette.chrome.deemph} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
      ))}
      {segments(split, values.length).map((pts, i) => (
        <polyline key={`h${i}`} points={pts} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      ))}
    </svg>
  )
}

export function formatPlain(decimals = 0) {
  return (v: number | null) => formatNumber(v, decimals)
}
