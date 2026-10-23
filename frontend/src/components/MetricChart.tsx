import type { Bucket, MetricDef, Person, SeriesResponse } from '../lib/types'
import { useUnits } from '../lib/units'
import {
  ChartCard,
  mergeSeries,
  PeopleBarChart,
  PeopleLegend,
  PeopleLineChart,
  PeopleTable,
  personKey,
  type Row,
} from './charts'

/** Metrics on a 0-100 scale: never draw the axis past 100. */
const HUNDRED_SCALE = new Set(['sleep_score', 'bb_max', 'bb_min', 'bb_charged', 'spo2', 'stress_avg'])

function periodAverage(rows: Row[], person: Person): number | null {
  const values = rows.map((r) => r[personKey(person)]).filter((v): v is number => typeof v === 'number')
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null
}

/** One metric, every selected person, with legend averages and a table twin. */
export function MetricChart({
  metric,
  people,
  response,
  bucket,
  kind = 'line',
  loading,
  connectNulls,
  referenceY,
  height,
  subtitle,
}: {
  metric: MetricDef | undefined
  people: Person[]
  response: SeriesResponse | undefined
  bucket: Bucket
  kind?: 'line' | 'bar'
  loading?: boolean
  connectNulls?: boolean
  referenceY?: number
  height?: number
  subtitle?: string
}) {
  const units = useUnits()
  if (!metric) return null
  // Values arrive metric; show them in the viewer's units.
  const shown = units.metric(metric)
  const visible = people.filter((p) => !response?.people[String(p.id)]?.hidden.includes(metric.key))
  const hiddenNames = people.filter((p) => !visible.includes(p)).map((p) => p.name)
  const rows = mergeSeries(response, visible, metric.key, (v) => shown.toDisplay(v))
  const format = (v: number | null) => shown.format(v)
  const per = metric.agg === 'sum' ? (bucket === 'day' ? 'per day' : `per ${bucket}`) : ''
  const legendValues: Record<number, string> = {}
  for (const person of visible) {
    const avg = periodAverage(rows, person)
    if (avg !== null) legendValues[person.id] = `avg ${format(avg)}`
  }
  const notes = [subtitle ?? (per ? `Total ${per}` : bucket !== 'day' ? `${bucket === 'week' ? 'Weekly' : 'Monthly'} average` : undefined)]
  if (hiddenNames.length) notes.push(`${hiddenNames.join(', ')} not shared`)

  return (
    <ChartCard
      title={metric.label + (shown.def.unit ? ` (${shown.def.unit})` : '')}
      subtitle={notes.filter(Boolean).join(' · ') || undefined}
      legend={<PeopleLegend people={visible} values={legendValues} shape={kind === 'bar' ? 'rect' : 'line'} />}
      loading={loading}
      empty={!loading && rows.length === 0}
      table={<PeopleTable rows={rows} people={visible} bucket={bucket} format={format} />}
    >
      {kind === 'bar' ? (
        <PeopleBarChart rows={rows} people={visible} metric={shown.def} format={format} bucket={bucket} height={height} referenceY={referenceY} />
      ) : (
        <PeopleLineChart
          rows={rows}
          people={visible}
          metric={shown.def}
          format={format}
          bucket={bucket}
          height={height}
          connectNulls={connectNulls}
          referenceY={referenceY}
          yFormat={shown.isClock ? (v) => shown.format(v) : undefined}
          yDomain={HUNDRED_SCALE.has(metric.key) ? ['auto', (max: number) => Math.min(100, Math.ceil(max / 5) * 5)] : undefined}
        />
      )}
    </ChartCard>
  )
}
