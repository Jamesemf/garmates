import { useState } from 'react'
import { Link } from 'react-router'
import { ChartCard, DataTable, PeopleBarChart, PeopleLegend, PeopleLineChart, PeopleTable, personKey, type Row } from '../components/charts'
import { FilterBar } from '../components/FilterBar'
import { MetricChart } from '../components/MetricChart'
import { PageHeader, PersonKey, Segmented } from '../components/ui'
import {
  formatDay,
  formatDistance,
  formatDuration,
  formatLongDay,
  formatNumber,
  formatPace,
  formatSpeed,
  SPORT_LABELS,
} from '../lib/format'
import { useActivities, useCatalog, useFilters, useSeries, useWorkoutStats } from '../lib/hooks'
import { usePalette } from '../lib/theme'
import type { Activity, Bucket, Person, SportStats, WorkoutStats } from '../lib/types'

const SPORTS = ['all', 'run', 'ride', 'swim', 'walk', 'strength', 'other'] as const
type Sport = (typeof SPORTS)[number]
type Measure = 'hours' | 'km' | 'load' | 'count'

const MEASURES: { value: Measure; label: string; unit: string; decimals: number }[] = [
  { value: 'hours', label: 'Time', unit: 'h', decimals: 1 },
  { value: 'km', label: 'Distance', unit: 'km', decimals: 1 },
  { value: 'load', label: 'Load', unit: '', decimals: 0 },
  { value: 'count', label: 'Sessions', unit: '', decimals: 0 },
]

function sumSports(sports: Record<string, SportStats>, sport: Sport, measure: Measure): number {
  return Object.entries(sports)
    .filter(([key]) => sport === 'all' || key === sport)
    .reduce((total, [, stats]) => total + stats[measure], 0)
}

export function WorkoutsPage() {
  const filters = useFilters('90d')
  const { byKey } = useCatalog()
  const [sport, setSport] = useState<Sport>('all')
  const [measure, setMeasure] = useState<Measure>('hours')
  const volumeBucket: Bucket = filters.bucket === 'day' ? 'week' : filters.bucket
  const stats = useWorkoutStats(filters.people, filters.start, filters.end, volumeBucket)
  const activities = useActivities(filters.people, filters.start, filters.end, sport === 'all' ? undefined : sport)
  const vo2 = useSeries(filters.people, ['vo2max'], filters.start, filters.end, filters.bucket)

  const shared = filters.people.filter((p) => stats.data && !stats.data.people[String(p.id)]?.hidden)
  const measureDef = MEASURES.find((m) => m.value === measure)!

  // Volume rows: one per bucket, one column per person.
  const volume = new Map<string, Row>()
  for (const person of shared) {
    for (const bucket of stats.data?.people[String(person.id)]?.buckets ?? []) {
      const row = volume.get(bucket.date) ?? { date: bucket.date }
      row[personKey(person)] = Math.round(sumSports(bucket.sports, sport, measure) * 10) / 10
      volume.set(bucket.date, row)
    }
  }
  const volumeRows = [...volume.values()].sort((a, b) => a.date.localeCompare(b.date))
  for (const row of volumeRows) for (const p of shared) row[personKey(p)] ??= 0
  const formatVolume = (v: number | null) =>
    v === null ? '–' : `${formatNumber(v, measureDef.decimals)}${measureDef.unit ? ` ${measureDef.unit}` : ''}`
  const totals: Record<number, string> = {}
  for (const p of shared) {
    const by = stats.data?.people[String(p.id)]?.by_sport ?? {}
    totals[p.id] = `total ${formatVolume(sumSports(by, sport, measure))}`
  }

  return (
    <>
      <PageHeader title="Workouts" subtitle="Training volume, intensity and fitness, side by side." />
      <FilterBar filters={filters} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Segmented
          label="Sport"
          value={sport}
          onChange={setSport}
          options={SPORTS.map((s) => ({ value: s, label: s === 'all' ? 'All sports' : SPORT_LABELS[s] }))}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title={`${measureDef.label} per ${volumeBucket}`}
          subtitle={sport === 'all' ? 'All sports' : SPORT_LABELS[sport]}
          legend={
            <div className="flex flex-wrap items-center justify-between gap-2">
              <PeopleLegend people={shared} values={totals} shape="rect" />
              <Segmented label="Measure" value={measure} onChange={setMeasure} options={MEASURES.map(({ value, label }) => ({ value, label }))} />
            </div>
          }
          loading={stats.isFetching}
          empty={!stats.isFetching && volumeRows.length === 0}
          table={<PeopleTable rows={volumeRows} people={shared} bucket={volumeBucket} format={formatVolume} />}
        >
          <PeopleBarChart rows={volumeRows} people={shared} bucket={volumeBucket} format={formatVolume} />
        </ChartCard>

        <MetricChart
          metric={byKey.vo2max}
          people={filters.people}
          response={vo2.data}
          bucket={filters.bucket}
          loading={vo2.isFetching}
          connectNulls
          subtitle="Garmin's estimate, recorded with runs and rides"
        />
      </div>

      <h2 className="mt-8 mb-3 text-sm font-semibold text-ink">Training load</h2>
      <div className="grid gap-4 lg:grid-cols-2">
        {shared.map((person) => (
          <LoadChart key={person.id} person={person} stats={stats.data?.people[String(person.id)]} loading={stats.isFetching} />
        ))}
      </div>

      <h2 className="mt-8 mb-3 text-sm font-semibold text-ink">Heart-rate zones</h2>
      <ZoneBars people={shared} stats={stats.data?.people} />

      <h2 className="mt-8 mb-3 text-sm font-semibold text-ink">
        Activities <span className="font-normal text-ink-2">({activities.data?.activities.length ?? 0})</span>
      </h2>
      <ActivityTable activities={activities.data?.activities ?? []} people={filters.people} />
    </>
  )
}

function LoadChart({ person, stats, loading }: { person: Person; stats?: WorkoutStats; loading: boolean }) {
  const palette = usePalette()
  const rows = (stats?.load ?? []).map((p) => ({ date: p.date, acute: p.acute, chronic: p.chronic, ratio: p.ratio }))
  const last = rows.at(-1)
  const ratio = last?.ratio ?? null
  const zone =
    ratio === null ? null : ratio < 0.8 ? 'Detraining' : ratio <= 1.3 ? 'Productive range' : ratio <= 1.5 ? 'Ramping up fast' : 'High injury risk'
  const loadPeople = [
    { ...person, id: -1, name: 'Acute (7 days)' },
    { ...person, id: -2, name: 'Chronic (28-day weekly avg)' },
  ]
  const chartRows: Row[] = rows.map((r) => ({ date: r.date, 'p-1': r.acute, 'p-2': r.chronic }))
  return (
    <ChartCard
      title={person.name}
      subtitle={
        ratio === null
          ? 'Acute vs chronic load (approximation from activity training load)'
          : `Acute:chronic ratio ${formatNumber(ratio, 2)} · ${zone}`
      }
      loading={loading}
      empty={!loading && rows.length === 0}
      legend={
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
          <li className="flex items-center gap-1.5">
            <span aria-hidden className="inline-block h-0.5 w-3 rounded" style={{ background: palette.series(person.color_slot) }} />
            Acute (last 7 days)
          </li>
          <li className="flex items-center gap-1.5">
            <span aria-hidden className="inline-block h-0.5 w-3 rounded" style={{ background: palette.chrome.muted }} />
            Chronic (28-day, per week)
          </li>
        </ul>
      }
      table={
        <DataTable
          columns={[
            { key: 'date', label: 'Date', format: (v) => formatDay(String(v)) },
            { key: 'acute', label: 'Acute' },
            { key: 'chronic', label: 'Chronic' },
            { key: 'ratio', label: 'Ratio', format: (v) => formatNumber(v as number | null, 2) },
          ]}
          rows={[...rows].reverse()}
        />
      }
    >
      {/* Acute in the person's colour, chronic in grey: one series is the point, the other is context. */}
      <PeopleLineChart
        rows={chartRows}
        people={loadPeople}
        format={(v) => formatNumber(v, 0)}
        height={200}
        colorFor={(p) => (p.id === -1 ? palette.series(person.color_slot) : palette.chrome.muted)}
      />
    </ChartCard>
  )
}

function ZoneBars({ people, stats }: { people: Person[]; stats?: Record<string, WorkoutStats> }) {
  const palette = usePalette()
  const zoneNames = ['Z1 Warm-up', 'Z2 Easy', 'Z3 Aerobic', 'Z4 Threshold', 'Z5 Maximum']
  const rows = people.map((p) => {
    const minutes = stats?.[String(p.id)]?.zone_minutes ?? [0, 0, 0, 0, 0]
    return { person: p, minutes, total: minutes.reduce((a, b) => a + b, 0) }
  })
  return (
    <ChartCard
      title="Time in heart-rate zones"
      subtitle="Share of workout time in each zone, using each person's own zones"
      legend={
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
          {zoneNames.map((name, i) => (
            <li key={name} className="flex items-center gap-1.5">
              <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: palette.ramp[i] }} />
              {name}
            </li>
          ))}
        </ul>
      }
      empty={rows.every((r) => r.total === 0)}
      table={
        <DataTable
          columns={[
            { key: 'name', label: 'Person' },
            ...zoneNames.map((z, i) => ({ key: `z${i}`, label: z, format: (v: unknown) => `${formatNumber(v as number)} min` })),
          ]}
          rows={rows.map((r) => ({ name: r.person.name, ...Object.fromEntries(r.minutes.map((m, i) => [`z${i}`, m])) }))}
        />
      }
    >
      <div className="space-y-3">
        {rows.map(({ person, minutes, total }) => (
          <div key={person.id} className="grid grid-cols-[8rem_minmax(0,1fr)] items-center gap-3 text-sm">
            <PersonKey person={person} className="text-ink-2" />
            <div className="flex h-6 w-full overflow-hidden rounded" role="img" aria-label={`${person.name}: ${minutes.map((m, i) => `${zoneNames[i]} ${Math.round(m)} minutes`).join(', ')}`}>
              {total > 0 &&
                minutes.map((m, i) => {
                  const share = m / total
                  if (share <= 0) return null
                  const darkFill = palette.mode === 'light' ? i >= 2 : i <= 2
                  return (
                    <div
                      key={i}
                      title={`${zoneNames[i]}: ${Math.round(m)} min (${Math.round(share * 100)}%)`}
                      className="flex h-full items-center justify-center text-[11px] font-medium"
                      style={{
                        width: `${share * 100}%`,
                        background: palette.ramp[i],
                        borderRight: i < 4 ? `2px solid ${palette.chrome.surface}` : undefined,
                        color: darkFill ? '#ffffff' : '#0b0b0b',
                      }}
                    >
                      {share >= 0.1 ? `${Math.round(share * 100)}%` : ''}
                    </div>
                  )
                })}
            </div>
          </div>
        ))}
      </div>
    </ChartCard>
  )
}

function ActivityTable({ activities, people }: { activities: Activity[]; people: Person[] }) {
  const byId = new Map(people.map((p) => [p.id, p]))
  if (!activities.length) return <p className="text-sm text-ink-2">No activities in this period.</p>
  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead className="text-xs text-ink-2">
          <tr>
            {['Date', 'Who', 'Activity', 'Distance', 'Time', 'Pace / speed', 'Avg HR', 'Load'].map((h) => (
              <th key={h} scope="col" className="px-4 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular">
          {activities.map((a) => {
            const person = byId.get(a.person_id)
            return (
              <tr key={a.activity_id} className="border-t border-line hover:bg-wash">
                <td className="px-4 py-2 whitespace-nowrap text-ink-2">{formatLongDay(a.date)}</td>
                <td className="px-4 py-2">{person && <PersonKey person={person} className="text-ink-2" />}</td>
                <td className="px-4 py-2">
                  <Link to={`/workouts/${a.activity_id}`} className="font-medium text-ink hover:underline">
                    {a.name ?? SPORT_LABELS[a.sport]}
                  </Link>
                  {a.is_pr && <span className="ml-2 text-xs text-ink-2">PR</span>}
                </td>
                <td className="px-4 py-2 text-ink">{formatDistance(a.distance_m)}</td>
                <td className="px-4 py-2 text-ink">{formatDuration(a.duration_s)}</td>
                <td className="px-4 py-2 text-ink">{a.sport === 'run' || a.sport === 'walk' ? formatPace(a.avg_speed_mps) : formatSpeed(a.avg_speed_mps)}</td>
                <td className="px-4 py-2 text-ink">{a.avg_hr ? `${Math.round(a.avg_hr)} bpm` : '–'}</td>
                <td className="px-4 py-2 text-ink">{formatNumber(a.training_load)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
