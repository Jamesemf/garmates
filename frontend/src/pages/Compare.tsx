import { useState } from 'react'
import { ChartCard, mergeSeries, PeopleLegend, PeopleLineChart, PeopleTable } from '../components/charts'
import { FilterBar } from '../components/FilterBar'
import { DeltaChip } from '../components/MetricCompareCard'
import { PageHeader, PersonKey, Segmented } from '../components/ui'
import { formatNumber } from '../lib/format'
import { useCatalog, useFilters, useSeries, useSummary } from '../lib/hooks'
import type { MetricDef, MetricSummary, Person } from '../lib/types'
import { useUnits } from '../lib/units'

type Mode = 'raw' | 'relative'

const BASELINE_DAYS = 30

export function ComparePage() {
  const filters = useFilters('30d')
  const catalog = useCatalog()
  const [mode, setMode] = useState<Mode>('relative')
  const [indexMetric, setIndexMetric] = useState('hrv')
  const units = useUnits()
  const show = (metric: MetricDef, value: number | null | undefined) => {
    const shown = units.metric(metric)
    return shown.format(value === null || value === undefined ? null : shown.toDisplay(value))
  }
  const metrics = catalog.data?.metrics ?? []
  const keys = metrics.map((m) => m.key)
  const summary = useSummary(filters.people, keys, filters.start, filters.end, BASELINE_DAYS)
  const people = filters.people

  const entry = (person: Person, key: string): MetricSummary | undefined =>
    summary.data?.people[String(person.id)]?.metrics[key]
  const isHidden = (person: Person, key: string) =>
    summary.data?.people[String(person.id)]?.hidden.includes(key) ?? false

  /** Who leads: best raw value, or the biggest move in the good direction vs their own usual. */
  const leader = (metric: MetricDef): number | null => {
    if (metric.direction === 'none' || people.length < 2) return null
    const sign = metric.direction === 'up' ? 1 : -1
    let best: { id: number; score: number } | null = null
    for (const person of people) {
      const s = entry(person, metric.key)
      const score = mode === 'raw' ? s?.value : s?.z
      if (score === null || score === undefined || isHidden(person, metric.key)) continue
      if (!best || sign * score > sign * best.score) best = { id: person.id, score }
    }
    // "Most improved" only when the move is meaningful (half a typical day-to-day swing).
    if (mode === 'relative' && best && sign * best.score < 0.5) return null
    return best?.id ?? null
  }

  return (
    <>
      <PageHeader
        title="Compare"
        subtitle={
          mode === 'raw'
            ? 'Period averages side by side.'
            : `Each person against their own previous ${BASELINE_DAYS} days - a fair comparison even when baselines differ.`
        }
        actions={
          <Segmented
            label="Comparison mode"
            value={mode}
            onChange={setMode}
            options={[
              { value: 'relative', label: 'vs own usual' },
              { value: 'raw', label: 'Raw values' },
            ]}
          />
        }
      />
      <FilterBar filters={filters} showBucket={false} />

      <IndexedChart
        metric={catalog.byKey[indexMetric]}
        metrics={metrics.filter((m) => m.direction !== 'none' || m.category === 'body')}
        onMetric={setIndexMetric}
        people={people}
        start={filters.start}
        end={filters.end}
        baselines={Object.fromEntries(people.map((p) => [p.id, entry(p, indexMetric)?.baseline ?? null]))}
      />

      <div className={`mt-6 overflow-x-auto rounded-xl border border-line bg-surface transition-opacity ${summary.isFetching ? 'opacity-60' : ''}`}>
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead>
            <tr className="text-xs text-ink-2">
              <th scope="col" className="px-4 py-3 font-medium">
                Metric
              </th>
              {people.map((p) => (
                <th key={p.id} scope="col" className="px-4 py-3 font-medium">
                  <PersonKey person={p} />
                </th>
              ))}
            </tr>
          </thead>
          {catalog.data?.categories.map((category) => (
            <tbody key={category.key}>
              <tr>
                <th colSpan={people.length + 1} scope="colgroup" className="bg-wash px-4 py-1.5 text-xs font-semibold text-ink-2">
                  {category.label}
                </th>
              </tr>
              {metrics
                .filter((m) => m.category === category.key)
                .map((metric) => {
                  const lead = leader(metric)
                  return (
                    <tr key={metric.key} className="border-t border-line">
                      <th scope="row" className="px-4 py-2 font-normal text-ink-2" title={metric.description || undefined}>
                        {metric.label}
                        {metric.agg === 'sum' && <span className="text-muted"> (per day)</span>}
                      </th>
                      {people.map((person) => {
                        const s = entry(person, metric.key)
                        if (isHidden(person, metric.key)) {
                          return (
                            <td key={person.id} className="px-4 py-2 text-muted">
                              Not shared
                            </td>
                          )
                        }
                        return (
                          <td key={person.id} className="px-4 py-2 align-top">
                            <div className="flex flex-wrap items-baseline gap-x-2">
                              <span className="font-semibold text-ink tabular">{show(metric, s?.value)}</span>
                              {mode === 'relative' && s?.value !== null && s && (
                                <DeltaChip metric={metric} summary={s} baselineDays={BASELINE_DAYS} />
                              )}
                              {lead === person.id && (
                                <span className="rounded border border-line px-1 text-[10px] font-semibold tracking-wide text-ink-2 uppercase">
                                  {mode === 'raw' ? 'Best' : 'Most improved'}
                                </span>
                              )}
                            </div>
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
            </tbody>
          ))}
        </table>
      </div>
    </>
  )
}

function IndexedChart({
  metric,
  metrics,
  onMetric,
  people,
  start,
  end,
  baselines,
}: {
  metric: MetricDef | undefined
  metrics: MetricDef[]
  onMetric: (key: string) => void
  people: Person[]
  start: string
  end: string
  baselines: Record<number, number | null>
}) {
  const units = useUnits()
  const series = useSeries(people, metric ? [metric.key] : [], start, end, 'day')
  if (!metric) return null
  const withBaseline = people.filter((p) => baselines[p.id])
  const rows = mergeSeries(series.data, withBaseline, metric.key, (value, person) =>
    Math.round((value / (baselines[person.id] as number)) * 1000) / 10,
  )
  const format = (v: number | null) => (v === null ? '–' : `${formatNumber(v, 1)}`)
  return (
    <ChartCard
      title={`${metric.label}, indexed to each person's usual (= 100)`}
      subtitle={`100 is that person's average over the ${BASELINE_DAYS} days before this period · ${
        metric.direction === 'up' ? 'above 100 is better' : metric.direction === 'down' ? 'below 100 is better' : 'neither direction is better'
      }`}
      legend={
        <div className="flex flex-wrap items-center justify-between gap-2">
          <PeopleLegend
            people={withBaseline}
            values={Object.fromEntries(withBaseline.map((p) => [p.id, `usual ${units.metric(metric).format(baselines[p.id] === null ? null : units.metric(metric).toDisplay(baselines[p.id] as number))}`]))}
          />
          <label className="flex items-center gap-2 text-xs text-ink-2">
            Metric
            <select
              value={metric.key}
              onChange={(e) => onMetric(e.target.value)}
              className="rounded-md border border-line bg-raised px-2 py-1 text-xs text-ink"
            >
              {metrics.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      }
      loading={series.isFetching}
      empty={!series.isFetching && rows.length === 0}
      table={<PeopleTable rows={rows} people={withBaseline} bucket="day" format={format} />}
    >
      <PeopleLineChart rows={rows} people={withBaseline} format={format} referenceY={100} height={240} />
    </ChartCard>
  )
}
