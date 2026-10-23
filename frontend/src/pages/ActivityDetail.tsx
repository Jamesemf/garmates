import { Link, useParams } from 'react-router'
import { ActivityMap } from '../components/ActivityMap'
import { ChartCard, DataTable, PeopleLineChart, type Row } from '../components/charts'
import { ErrorNote, PageHeader, PersonKey } from '../components/ui'
import {
  formatDistance,
  formatDuration,
  formatLongDay,
  formatNumber,
  formatPace,
  formatSpeed,
  SPORT_LABELS,
} from '../lib/format'
import { useActivity, usePeople } from '../lib/hooks'
import { usePalette } from '../lib/theme'
import type { Person } from '../lib/types'

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-ink-2">{label}</dt>
      <dd className="text-lg font-semibold text-ink">{value}</dd>
    </div>
  )
}

const elapsed = (seconds: string) => {
  const s = Number(seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return h ? `${h}:${String(m).padStart(2, '0')}` : `${m} min`
}

export function ActivityDetailPage() {
  const { activityId } = useParams()
  const { data: activity, isLoading, error } = useActivity(Number(activityId))
  const { data: people = [] } = usePeople()
  const palette = usePalette()

  if (isLoading) return <p className="text-sm text-ink-2">Loading activity (downloading the FIT file the first time)…</p>
  if (error || !activity) return <ErrorNote error={error ?? 'Activity not found'} />

  const person = people.find((p) => p.id === activity.person_id)
  const color = palette.series(person?.color_slot ?? 0)
  const pace = activity.sport === 'run' || activity.sport === 'walk'
  const points = activity.track.points
  const sample = (index: number, transform?: (v: number) => number): Row[] =>
    points
      .filter((p) => p[index] !== null)
      .map((p) => ({ date: String(p[0]), v: transform ? transform(p[index] as number) : (p[index] as number) }))
  const single: Person = person ? { ...person, id: 0 } : ({ id: 0, name: 'Value', color_slot: 0 } as Person)
  const toKey = (rows: Row[]) => rows.map((r) => ({ date: r.date, p0: r.v }))

  const hrRows = toKey(sample(3))
  const speedRows = toKey(sample(5, (v) => (pace ? (v > 0.5 ? 1000 / v / 60 : NaN) : v * 3.6)).filter((r) => Number.isFinite(r.v)))
  const altRows = toKey(sample(4))
  const zones = activity.hr_zone_s ?? []
  const zoneTotal = zones.reduce<number>((a, b) => a + (b ?? 0), 0)

  return (
    <>
      <Link to="/workouts" className="mb-3 inline-block text-sm text-ink-2 hover:text-ink">
        ← Workouts
      </Link>
      <PageHeader
        title={activity.name ?? SPORT_LABELS[activity.sport]}
        subtitle={
          <span className="inline-flex flex-wrap items-center gap-2">
            {person && <PersonKey person={person} />}
            <span>· {formatLongDay(activity.date)}</span>
            <span>· {SPORT_LABELS[activity.sport]}</span>
          </span>
        }
      />
      <dl className="mb-5 grid grid-cols-2 gap-4 rounded-xl border border-line bg-surface p-4 sm:grid-cols-4 lg:grid-cols-6">
        <Stat label="Distance" value={formatDistance(activity.distance_m)} />
        <Stat label="Time" value={formatDuration(activity.duration_s)} />
        <Stat label={pace ? 'Avg pace' : 'Avg speed'} value={pace ? formatPace(activity.avg_speed_mps) : formatSpeed(activity.avg_speed_mps)} />
        <Stat label="Avg / max HR" value={activity.avg_hr ? `${Math.round(activity.avg_hr)} / ${Math.round(activity.max_hr ?? 0)}` : '–'} />
        <Stat label="Elevation gain" value={activity.elevation_gain_m ? `${Math.round(activity.elevation_gain_m)} m` : '–'} />
        <Stat label="Calories" value={formatNumber(activity.calories)} />
        <Stat label="Training load" value={formatNumber(activity.training_load)} />
        <Stat label="Aerobic TE" value={formatNumber(activity.aerobic_te, 1)} />
        <Stat label="Anaerobic TE" value={formatNumber(activity.anaerobic_te, 1)} />
        <Stat label="VO2 max" value={formatNumber(activity.vo2max, 1)} />
        <Stat label="Cadence" value={activity.avg_cadence ? `${Math.round(activity.avg_cadence)}` : '–'} />
        <Stat label="Avg power" value={activity.avg_power ? `${Math.round(activity.avg_power)} W` : '–'} />
      </dl>

      {activity.track.error && (
        <p className="mb-4 text-sm text-ink-2">Couldn't load the detailed track: {activity.track.error}</p>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {points.some((p) => p[1] !== null) && (
          <section className="rounded-xl border border-line bg-surface p-4 lg:col-span-2">
            <ActivityMap points={points} color={color} />
          </section>
        )}
        {hrRows.length > 0 && (
          <ChartCard
            title="Heart rate (bpm)"
            table={<DataTable columns={[{ key: 'date', label: 'Elapsed', format: (v) => elapsed(String(v)) }, { key: 'p0', label: 'bpm' }]} rows={hrRows} />}
          >
            <PeopleLineChart rows={hrRows} people={[single]} xFormat={elapsed} format={(v) => `${formatNumber(v)} bpm`} height={200} />
          </ChartCard>
        )}
        {speedRows.length > 0 && (
          <ChartCard
            title={pace ? 'Pace (min/km)' : 'Speed (km/h)'}
            subtitle={pace ? 'Lower is faster' : undefined}
            table={<DataTable columns={[{ key: 'date', label: 'Elapsed', format: (v) => elapsed(String(v)) }, { key: 'p0', label: pace ? 'min/km' : 'km/h', format: (v) => formatNumber(v as number, 2) }]} rows={speedRows} />}
          >
            <PeopleLineChart rows={speedRows} people={[single]} xFormat={elapsed} format={(v) => formatNumber(v, 2)} height={200} />
          </ChartCard>
        )}
        {altRows.length > 0 && (
          <ChartCard
            title="Elevation (m)"
            table={<DataTable columns={[{ key: 'date', label: 'Elapsed', format: (v) => elapsed(String(v)) }, { key: 'p0', label: 'm' }]} rows={altRows} />}
          >
            <PeopleLineChart rows={altRows} people={[single]} xFormat={elapsed} format={(v) => `${formatNumber(v)} m`} height={200} />
          </ChartCard>
        )}
        {zoneTotal > 0 && (
          <ChartCard title="Time in zones">
            <ul className="space-y-2 text-sm">
              {zones.map((seconds, i) => (
                <li key={i} className="grid grid-cols-[5rem_minmax(0,1fr)_4rem] items-center gap-3">
                  <span className="text-ink-2">Zone {i + 1}</span>
                  <span className="h-3 rounded-r" style={{ width: `${((seconds ?? 0) / zoneTotal) * 100}%`, minWidth: seconds ? 4 : 0, background: palette.ramp[i] }} />
                  <span className="text-right text-ink tabular">{formatDuration(seconds ?? 0)}</span>
                </li>
              ))}
            </ul>
          </ChartCard>
        )}
      </div>
    </>
  )
}
