import { useState } from 'react'
import { Link } from 'react-router'
import { FilterBar } from '../components/FilterBar'
import { MetricCompareCard, type DisplayOptions } from '../components/MetricCompareCard'
import { EmptyState, PageHeader, PersonKey, Segmented } from '../components/ui'
import { addDays, formatDuration, formatLongDay, SPORT_LABELS, toIsoDay } from '../lib/format'
import { useActivities, useCatalog, useFilters, useSeries, useSummary } from '../lib/hooks'
import type { MetricSummary, Person } from '../lib/types'
import { useUnits } from '../lib/units'

const CARDS: { key: string; display?: DisplayOptions }[] = [
  { key: 'sleep_score' },
  { key: 'sleep_hours' },
  { key: 'hrv' },
  { key: 'rhr' },
  { key: 'bb_max' },
  { key: 'stress_avg' },
  { key: 'steps', display: { suffix: ' / day' } },
  { key: 'intensity_minutes', display: { factor: 7, suffix: ' min / wk' } },
  { key: 'workout_hours', display: { factor: 7, suffix: ' h / wk' } },
  { key: 'training_load', display: { factor: 7, suffix: ' / wk' } },
  { key: 'vo2max' },
  { key: 'weight' },
]

const PERIODS = [
  { value: '7', label: '7 days', baseline: 30 },
  { value: '14', label: '14 days', baseline: 60 },
  { value: '30', label: '30 days', baseline: 90 },
] as const

export function OverviewPage() {
  const filters = useFilters()
  const { byKey } = useCatalog()
  const [period, setPeriod] = useState<(typeof PERIODS)[number]['value']>('7')
  const { baseline } = PERIODS.find((p) => p.value === period)!
  const periodDays = Number(period)

  const end = toIsoDay(new Date())
  const start = addDays(end, -(periodDays - 1))
  const metrics = CARDS.map((c) => c.key)
  const people = filters.people

  const summary = useSummary(people, metrics, start, end, baseline)
  const trendStart = addDays(start, -Math.min(baseline, 30))
  const series = useSeries(people, metrics, trendStart, end, 'day')

  if (filters.allPeople.length === 0) {
    return (
      <>
        <PageHeader title="Overview" />
        <EmptyState title="No data yet">
          Add your Garmin Personal API key (or load the demo profiles) on the{' '}
          <Link to="/people" className="font-medium text-ink underline underline-offset-2">
            People &amp; keys
          </Link>{' '}
          page to get started.
        </EmptyState>
      </>
    )
  }

  const trendFor = (person: Person, key: string) => {
    const points = series.data?.people[String(person.id)]?.points ?? []
    const byDate = new Map(points.map((p) => [p.date, p[key]]))
    const values: (number | null)[] = []
    for (let d = trendStart; d <= end; d = addDays(d, 1)) {
      const v = byDate.get(d)
      values.push(typeof v === 'number' ? v : null)
    }
    return values
  }

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle={`Average over the last ${periodDays} days, compared with each person's own previous ${baseline} days.`}
        actions={
          <Segmented label="Period" value={period} options={PERIODS.map(({ value, label }) => ({ value, label }))} onChange={setPeriod} />
        }
      />
      <FilterBar filters={filters} showRange={false} showBucket={false} />

      <div className={`grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 transition-opacity ${summary.isFetching ? 'opacity-60' : ''}`}>
        {CARDS.map(({ key, display }) => {
          const metric = byKey[key]
          if (!metric) return null
          const summaries: Record<number, MetricSummary | undefined> = {}
          const hidden: Record<number, boolean> = {}
          const trends: Record<number, (number | null)[]> = {}
          for (const person of people) {
            const entry = summary.data?.people[String(person.id)]
            summaries[person.id] = entry?.metrics[key]
            hidden[person.id] = entry?.hidden.includes(key) ?? false
            trends[person.id] = trendFor(person, key)
          }
          return (
            <MetricCompareCard
              key={key}
              metric={metric}
              people={people}
              summaries={summaries}
              hidden={hidden}
              trends={trends}
              periodDays={periodDays}
              baselineDays={baseline}
              display={display}
            />
          )
        })}
      </div>

      <RecentWorkouts people={people} />
    </>
  )
}

function RecentWorkouts({ people }: { people: Person[] }) {
  const end = toIsoDay(new Date())
  const { data } = useActivities(people, addDays(end, -30), end)
  const units = useUnits()
  const byId = new Map(people.map((p) => [p.id, p]))
  const recent = (data?.activities ?? []).slice(0, 8)
  return (
    <section className="mt-6">
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-ink">Recent workouts</h2>
        <Link to="/workouts" className="text-xs font-medium text-ink-2 hover:text-ink">
          All workouts →
        </Link>
      </div>
      {recent.length === 0 ? (
        <p className="text-sm text-ink-2">No workouts in the last 30 days.</p>
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
          {recent.map((a) => {
            const person = byId.get(a.person_id)
            return (
              <li key={a.activity_id}>
                <Link to={`/workouts/${a.activity_id}`} className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 px-4 py-2.5 hover:bg-wash sm:grid-cols-[10rem_minmax(0,1fr)_auto]">
                  {person && <PersonKey person={person} className="text-xs text-ink-2 sm:text-sm" />}
                  <span className="min-w-0 truncate text-sm text-ink sm:order-none">
                    <span className="font-medium">{a.name ?? SPORT_LABELS[a.sport]}</span>
                    <span className="text-ink-2"> · {formatLongDay(a.date)}</span>
                  </span>
                  <span className="col-start-2 row-span-2 row-start-1 self-center text-right text-sm text-ink-2 tabular sm:col-start-auto sm:row-span-1">
                    {a.distance_m ? `${units.distance(a.distance_m)} · ` : ''}
                    {formatDuration(a.duration_s)}
                  </span>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
