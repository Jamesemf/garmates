import { useSearchParams } from 'react-router'
import { ChartCard, PeopleLegend, PeopleLineChart, PeopleTable, personKey, type Row } from '../components/charts'
import { FilterBar } from '../components/FilterBar'
import { Button, inputClass, PageHeader, PersonKey } from '../components/ui'
import { addDays, formatDuration, formatLongDay, formatNumber, toIsoDay } from '../lib/format'
import { useDay, useFilters } from '../lib/hooks'
import { usePalette } from '../lib/theme'
import type { DayPerson, Person } from '../lib/types'

const SLOT_MINUTES = 6

/** Round 3-hourly ticks that actually exist in the overlaid rows. */
function hourTicks(rows: Row[]): string[] {
  const present = new Set(rows.map((r) => r.date))
  return Array.from({ length: 8 }, (_, i) => String(i * 180)).filter((t) => present.has(t))
}

function timeOfDay(minutes: string | number): string {
  const m = Number(minutes)
  return `${String(Math.floor(m / 60) % 24).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
}

/** Overlay intraday series by local time of day, in fixed slots so people line up. */
function overlay(people: Person[], day: Record<string, DayPerson> | undefined, field: 'heart_rate' | 'body_battery'): Row[] {
  const slots = new Map<number, Row>()
  for (const person of people) {
    const sums = new Map<number, { total: number; n: number }>()
    for (const [ts, value] of day?.[String(person.id)]?.[field] ?? []) {
      const t = new Date(ts)
      const slot = Math.floor((t.getHours() * 60 + t.getMinutes()) / SLOT_MINUTES) * SLOT_MINUTES
      const acc = sums.get(slot) ?? { total: 0, n: 0 }
      acc.total += value
      acc.n += 1
      sums.set(slot, acc)
    }
    for (const [slot, { total, n }] of sums) {
      const row = slots.get(slot) ?? { date: String(slot) }
      row[personKey(person)] = Math.round(total / n)
      slots.set(slot, row)
    }
  }
  return [...slots.entries()].sort((a, b) => a[0] - b[0]).map(([, row]) => row)
}

export function DayPage() {
  const filters = useFilters()
  const [params, setParams] = useSearchParams()
  const today = toIsoDay(new Date())
  const date = params.get('date') ?? today
  const setDate = (value: string) => {
    const next = new URLSearchParams(params)
    next.set('date', value)
    setParams(next, { replace: true })
  }
  const { data, isFetching } = useDay(filters.people, date)
  const people = filters.people
  const hrRows = overlay(people, data?.people, 'heart_rate')
  const bbRows = overlay(people, data?.people, 'body_battery')
  const hrPeople = people.filter((p) => data?.people[String(p.id)]?.heart_rate?.length)
  const bbPeople = people.filter((p) => data?.people[String(p.id)]?.body_battery?.length)

  return (
    <>
      <PageHeader
        title="Day view"
        subtitle={formatLongDay(date)}
        actions={
          <div className="flex items-center gap-2">
            <Button onClick={() => setDate(addDays(date, -1))} aria-label="Previous day">
              ←
            </Button>
            <input
              type="date"
              aria-label="Date"
              value={date}
              max={today}
              onChange={(e) => e.target.value && setDate(e.target.value)}
              className={`${inputClass} w-auto py-1.5`}
            />
            <Button onClick={() => setDate(addDays(date, 1))} disabled={date >= today} aria-label="Next day">
              →
            </Button>
          </div>
        }
      />
      <FilterBar filters={filters} showRange={false} showBucket={false} />

      <div className={`grid gap-3 sm:grid-cols-2 xl:grid-cols-3 transition-opacity ${isFetching ? 'opacity-60' : ''}`}>
        {people.map((person) => (
          <DaySummary key={person.id} person={person} entry={data?.people[String(person.id)]} />
        ))}
      </div>

      <SleepWindows people={people} day={data?.people} date={date} />

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Heart rate through the day (bpm)"
          subtitle={`${SLOT_MINUTES}-minute averages, local time`}
          legend={<PeopleLegend people={hrPeople} />}
          loading={isFetching}
          empty={!isFetching && hrRows.length === 0}
          table={<PeopleTable rows={hrRows} people={hrPeople} bucket="day" format={(v) => formatNumber(v)} />}
        >
          <PeopleLineChart rows={hrRows} people={hrPeople} xFormat={timeOfDay} xTicks={hourTicks(hrRows)} format={(v) => `${formatNumber(v)} bpm`} connectNulls />
        </ChartCard>
        <ChartCard
          title="Body Battery through the day"
          subtitle="Charges during rest and sleep, drains with activity and stress"
          legend={<PeopleLegend people={bbPeople} />}
          loading={isFetching}
          empty={!isFetching && bbRows.length === 0}
          table={<PeopleTable rows={bbRows} people={bbPeople} bucket="day" format={(v) => formatNumber(v)} />}
        >
          <PeopleLineChart rows={bbRows} people={bbPeople} xFormat={timeOfDay} xTicks={hourTicks(bbRows)} format={(v) => formatNumber(v)} yDomain={[0, 100]} connectNulls />
        </ChartCard>
      </div>
      {people.some((p) => data?.people[String(p.id)]?.detail_error) && (
        <p className="mt-3 text-xs text-ink-2">
          Some intraday data couldn't be fetched from Garmin:{' '}
          {people
            .map((p) => data?.people[String(p.id)]?.detail_error && `${p.name}: ${data.people[String(p.id)].detail_error}`)
            .filter(Boolean)
            .join(' · ')}
        </p>
      )}
    </>
  )
}

function DaySummary({ person, entry }: { person: Person; entry?: DayPerson }) {
  const sleep = entry?.sleep
  const items: [string, string][] = [
    ['Sleep score', formatNumber(sleep?.score ?? null)],
    ['Slept', formatDuration(sleep?.duration_s ?? null)],
    ['Overnight HRV', entry?.hrv?.last_night_avg ? `${entry.hrv.last_night_avg} ms` : '–'],
    ['Resting HR', entry?.daily?.rhr ? `${entry.daily.rhr} bpm` : '–'],
    ['Body Battery', entry?.daily?.bb_max ? `${entry.daily.bb_min ?? '–'} → ${entry.daily.bb_max}` : '–'],
    ['Steps', formatNumber(entry?.daily?.steps ?? null)],
  ]
  return (
    <section className="rounded-xl border border-line bg-surface p-4">
      <PersonKey person={person} className="mb-3 text-sm font-semibold text-ink" />
      <dl className="grid grid-cols-3 gap-3">
        {items.map(([label, value]) => (
          <div key={label} className="min-w-0">
            <dt className="truncate text-xs text-ink-2">{label}</dt>
            <dd className="text-base font-semibold text-ink">{value}</dd>
          </div>
        ))}
      </dl>
      {entry?.hidden?.length ? <p className="mt-2 text-xs text-muted">Some data not shared</p> : null}
    </section>
  )
}

/** Bedtime → wake bars on one clock, so everyone's night lines up. */
function SleepWindows({ people, day, date }: { people: Person[]; day?: Record<string, DayPerson>; date: string }) {
  const palette = usePalette()
  // Axis: 18:00 the evening before → 14:00 on the day (20 hours).
  const axisStart = new Date(`${addDays(date, -1)}T18:00:00`).getTime()
  const span = 20 * 3600 * 1000
  const windows = people
    .map((person) => {
      const sleep = day?.[String(person.id)]?.sleep
      if (!sleep?.start_local || !sleep.end_local) return null
      const start = new Date(sleep.start_local).getTime()
      const end = new Date(sleep.end_local).getTime()
      return { person, start, end, left: ((start - axisStart) / span) * 100, width: ((end - start) / span) * 100 }
    })
    .filter((w): w is NonNullable<typeof w> => w !== null)
  if (!windows.length) return null
  const ticks = [18, 21, 0, 3, 6, 9, 12]
  const clock = (ms: number) => new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return (
    <ChartCard title="Sleep window" subtitle="Bedtime to wake, local time" className="mt-4">
      <div className="space-y-2.5">
        {windows.map((w) => (
          <div key={w.person.id} className="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-3 text-sm">
            <PersonKey person={w.person} className="text-ink-2" />
            <div className="relative h-6 rounded bg-wash">
              <div
                className="absolute top-0 flex h-full items-center justify-center overflow-visible rounded"
                style={{ left: `${Math.max(0, w.left)}%`, width: `${Math.min(100 - Math.max(0, w.left), w.width)}%`, background: palette.series(w.person.color_slot) }}
                title={`${clock(w.start)} – ${clock(w.end)}`}
              />
              <span className="absolute top-1/2 -translate-y-1/2 pl-1 text-xs whitespace-nowrap text-ink" style={{ left: `${Math.min(80, Math.max(0, w.left + w.width))}%` }}>
                {clock(w.start)} – {clock(w.end)}
              </span>
            </div>
          </div>
        ))}
        <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-3">
          <span />
          <div className="relative h-4 text-[11px] text-muted tabular">
            {ticks.map((h, i) => {
              const offset = ((h - 18 + 24) % 24) / 20
              return (
                <span key={h} className="absolute -translate-x-1/2" style={{ left: `${offset * 100}%` }}>
                  {i === 0 || h === 0 || h === 12 ? `${String(h).padStart(2, '0')}:00` : String(h).padStart(2, '0')}
                </span>
              )
            })}
          </div>
        </div>
      </div>
    </ChartCard>
  )
}
