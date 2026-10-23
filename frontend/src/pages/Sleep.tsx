import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ChartCard, DataTable } from '../components/charts'
import { FilterBar } from '../components/FilterBar'
import { MetricChart } from '../components/MetricChart'
import { PageHeader, PersonKey } from '../components/ui'
import { formatDay, formatNumber } from '../lib/format'
import { useCatalog, useFilters, useSeries } from '../lib/hooks'
import { usePalette } from '../lib/theme'
import type { Bucket, Person, SeriesResponse } from '../lib/types'

const METRICS = [
  'sleep_score',
  'sleep_hours',
  'deep_hours',
  'rem_hours',
  'light_hours',
  'awake_minutes',
  'hrv',
  'rhr',
  'bb_max',
  'bb_charged',
  'stress_avg',
  'bedtime',
  'wake_time',
]

export function SleepPage() {
  const filters = useFilters()
  const { byKey } = useCatalog()
  // Sleep values are levels, so roll up as averages even when the period is long.
  const series = useSeries(filters.people, METRICS, filters.start, filters.end, filters.bucket)
  const common = { people: filters.people, response: series.data, bucket: filters.bucket, loading: series.isFetching }

  return (
    <>
      <PageHeader title="Sleep & recovery" subtitle="How well everyone is sleeping and recovering." />
      <FilterBar filters={filters} />
      <div className="grid gap-4 lg:grid-cols-2">
        <MetricChart metric={byKey.sleep_score} {...common} />
        <MetricChart metric={byKey.sleep_hours} {...common} />
        <MetricChart metric={byKey.hrv} {...common} subtitle="Higher than your own usual is generally a sign of good recovery" />
        <MetricChart metric={byKey.rhr} {...common} subtitle="Lower than your own usual is generally better" />
        <MetricChart metric={byKey.bb_max} {...common} subtitle="Peak Body Battery each day" />
        <MetricChart metric={byKey.stress_avg} {...common} />
        <MetricChart metric={byKey.bedtime} {...common} subtitle="When sleep started - a steadier line means a more regular routine" />
        <MetricChart metric={byKey.wake_time} {...common} />
      </div>
      <h2 className="mt-8 mb-3 text-sm font-semibold text-ink">Sleep stages</h2>
      <div className="grid gap-4 lg:grid-cols-2">
        {filters.people.map((person) => (
          <SleepStages key={person.id} person={person} response={series.data} bucket={filters.bucket} loading={series.isFetching} />
        ))}
      </div>
    </>
  )
}

function SleepStages({
  person,
  response,
  bucket,
  loading,
}: {
  person: Person
  response: SeriesResponse | undefined
  bucket: Bucket
  loading: boolean
}) {
  const palette = usePalette()
  const entry = response?.people[String(person.id)]
  const hidden = entry?.hidden.includes('deep_hours')
  const rows = (entry?.points ?? [])
    .filter((p) => typeof p.deep_hours === 'number')
    .map((p) => ({
      date: p.date,
      deep_hours: p.deep_hours as number,
      rem_hours: (p.rem_hours as number) ?? 0,
      light_hours: (p.light_hours as number) ?? 0,
      awake_hours: typeof p.awake_minutes === 'number' ? p.awake_minutes / 60 : 0,
    }))
  const colors = { deep_hours: palette.ramp[4], rem_hours: palette.ramp[2], light_hours: palette.ramp[0], awake_hours: palette.chrome.neutral }
  const labels = { deep_hours: 'Deep', rem_hours: 'REM', light_hours: 'Light', awake_hours: 'Awake' }
  const keys = ['deep_hours', 'rem_hours', 'light_hours', 'awake_hours'] as const

  return (
    <ChartCard
      title={`${person.name}`}
      subtitle={hidden ? 'Not shared' : `Hours per night${bucket !== 'day' ? `, ${bucket}ly average` : ''}`}
      loading={loading}
      empty={!loading && (hidden || rows.length === 0)}
      legend={
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
          <PersonKey person={person} className="font-medium text-ink" />
          {keys.map((k) => (
            <span key={k} className="flex items-center gap-1.5">
              <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: colors[k] }} />
              {labels[k]}
            </span>
          ))}
        </div>
      }
      table={
        <DataTable
          columns={[
            { key: 'date', label: 'Date', format: (v) => formatDay(String(v), bucket) },
            ...keys.map((k) => ({ key: k, label: labels[k], format: (v: unknown) => formatNumber(v as number, 1) })),
          ]}
          rows={[...rows].reverse()}
        />
      }
    >
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }} barCategoryGap="18%">
          <CartesianGrid vertical={false} stroke={palette.chrome.grid} />
          <XAxis dataKey="date" tickFormatter={(v: string) => formatDay(v, bucket)} tickLine={false} axisLine={{ stroke: palette.chrome.axis }} minTickGap={20} tickMargin={6} />
          <YAxis width={32} tickLine={false} axisLine={false} />
          <Tooltip
            cursor={{ fill: palette.mode === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(11,11,11,0.04)' }}
            isAnimationActive={false}
            content={({ active, payload, label }) =>
              active && payload?.length ? (
                <div className="rounded-lg border border-line bg-raised px-3 py-2 text-xs shadow-lg">
                  <p className="mb-1 text-ink-2">{formatDay(String(label), bucket)}</p>
                  {[...payload].reverse().map((item) => (
                    <p key={String(item.dataKey)} className="flex items-center gap-2">
                      <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: colors[item.dataKey as keyof typeof colors] }} />
                      <span className="font-semibold text-ink tabular">{formatNumber(item.value as number, 1)} h</span>
                      <span className="text-ink-2">{labels[item.dataKey as keyof typeof labels]}</span>
                    </p>
                  ))}
                </div>
              ) : null
            }
          />
          {keys.map((k, i) => (
            <Bar
              key={k}
              dataKey={k}
              stackId="stages"
              fill={colors[k]}
              stroke={palette.chrome.surface}
              strokeWidth={1}
              maxBarSize={24}
              radius={i === keys.length - 1 ? [4, 4, 0, 0] : 0}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}
