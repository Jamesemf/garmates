import { formatNumber } from '../lib/format'
import { usePalette } from '../lib/theme'
import type { MetricDef, MetricSummary, Person } from '../lib/types'
import { Sparkline } from './charts'
import { cx } from './ui'

export interface DisplayOptions {
  /** Multiply the per-day value (e.g. ×7 to show weekly totals). */
  factor?: number
  suffix?: string
}

/** How a change compares with the person's own usual level. */
export function deltaTone(metric: MetricDef, summary: MetricSummary | undefined) {
  if (!summary || summary.delta_pct === null) return { tone: 'none' as const, arrow: '', text: '' }
  const pct = summary.delta_pct
  const small = Math.abs(pct) < 2 || (summary.z !== null && Math.abs(summary.z) < 0.5)
  if (small) return { tone: 'neutral' as const, arrow: '≈', text: 'usual' }
  const up = pct > 0
  const arrow = up ? '▲' : '▼'
  const text = `${Math.abs(pct).toFixed(Math.abs(pct) < 10 ? 1 : 0)}%`
  if (metric.direction === 'none') return { tone: 'neutral' as const, arrow, text }
  const good = (metric.direction === 'up') === up
  return { tone: good ? ('good' as const) : ('bad' as const), arrow, text }
}

export function DeltaChip({ metric, summary, baselineDays }: { metric: MetricDef; summary?: MetricSummary; baselineDays: number }) {
  const { tone, arrow, text } = deltaTone(metric, summary)
  if (tone === 'none') return <span className="text-xs text-muted">No baseline yet</span>
  const color = { good: 'text-good', bad: 'text-bad', neutral: 'text-ink-2' }[tone]
  const word = tone === 'good' ? 'better than' : tone === 'bad' ? 'worse than' : 'vs'
  return (
    <span className={cx('inline-flex items-center gap-1 text-xs font-medium whitespace-nowrap', color)} title={`Compared with this person's previous ${baselineDays} days`}>
      <span aria-hidden>{arrow}</span>
      {text}
      <span className="sr-only">
        {tone === 'neutral' && arrow === '≈' ? 'about the same as usual' : `${word} usual`}
      </span>
      {arrow !== '≈' && <span className="font-normal text-ink-2">vs usual</span>}
    </span>
  )
}

export function MetricCompareCard({
  metric,
  people,
  summaries,
  hidden,
  trends,
  periodDays,
  baselineDays,
  display,
}: {
  metric: MetricDef
  people: Person[]
  summaries: Record<number, MetricSummary | undefined>
  hidden: Record<number, boolean>
  trends: Record<number, (number | null)[]>
  periodDays: number
  baselineDays: number
  display?: DisplayOptions
}) {
  const palette = usePalette()
  const factor = display?.factor ?? 1
  const unit = display?.suffix ?? (metric.unit ? ` ${metric.unit}` : '')
  return (
    <section className="min-w-0 rounded-xl border border-line bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-ink" title={metric.description || undefined}>
        {metric.label}
      </h2>
      <ul className="space-y-3">
        {people.map((person) => {
          const summary = summaries[person.id]
          const isHidden = hidden[person.id]
          const value = summary?.value ?? null
          return (
            <li key={person.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-0.5">
              <span className="flex min-w-0 items-center gap-1.5 text-xs text-ink-2">
                <span aria-hidden className="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: palette.series(person.color_slot) }} />
                <span className="truncate">{person.name}</span>
              </span>
              {!isHidden && (
                <span className="row-span-2 self-center">
                  <Sparkline
                    values={trends[person.id] ?? []}
                    highlightFrom={(trends[person.id]?.length ?? 0) - periodDays}
                    color={palette.series(person.color_slot)}
                  />
                </span>
              )}
              {isHidden ? (
                <span className="col-span-2 text-sm text-muted">Not shared</span>
              ) : (
                <span className="flex min-w-0 flex-wrap items-baseline gap-x-2">
                  <span className="text-2xl font-semibold tracking-tight text-ink">
                    {value === null ? '–' : formatNumber(value * factor, metric.decimals)}
                    {value !== null && <span className="text-sm font-normal text-ink-2">{unit}</span>}
                  </span>
                  {value !== null && <DeltaChip metric={metric} summary={summary} baselineDays={baselineDays} />}
                </span>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
