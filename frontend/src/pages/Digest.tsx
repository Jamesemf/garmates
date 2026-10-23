import { useSearchParams, Link } from 'react-router'
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'
import { FilterBar } from '../components/FilterBar'
import { Button, Card, cx, EmptyState, PageHeader, PersonKey, StatusBadge } from '../components/ui'
import { addDays, formatDuration, formatLongDay, formatNumber, parseDay, SPORT_LABELS, toIsoDay } from '../lib/format'
import { useCatalog, useDigest, useFilters, useInsights } from '../lib/hooks'
import { usePalette } from '../lib/theme'
import type { DigestPerson, Highlight, Insight, MetricDef, Person } from '../lib/types'
import { usePrefs, useUnits } from '../lib/units'

const KPI_KEYS = ['sleep_score', 'sleep_hours', 'hrv', 'rhr', 'steps', 'intensity_minutes', 'workouts', 'workout_hours', 'training_load', 'stress_avg', 'bedtime']

const weekday = new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'short' })

export function DigestPage() {
  const filters = useFilters()
  const prefs = usePrefs()
  const [params, setParams] = useSearchParams()
  const week = params.get('week')
  const digest = useDigest(filters.people, week)
  const insights = useInsights(filters.people)
  const shownWeek = digest.data?.week

  const thisWeekStart = (() => {
    const d = parseDay(toIsoDay(new Date()))
    const offset = prefs.week_start === 'sunday' ? d.getDay() : (d.getDay() + 6) % 7
    return addDays(toIsoDay(d), -offset)
  })()
  const go = (deltaWeeks: number) => {
    if (!shownWeek) return
    const next = new URLSearchParams(params)
    next.set('week', addDays(shownWeek, deltaWeeks * 7))
    setParams(next, { replace: true })
  }
  const inProgress = shownWeek === thisWeekStart

  return (
    <>
      <PageHeader
        title="Weekly digest"
        subtitle={
          shownWeek
            ? `${formatLongDay(shownWeek)} – ${formatLongDay(digest.data!.week_end)}${inProgress ? ' (so far)' : ''} · compared with each person's previous 4 weeks`
            : undefined
        }
        actions={
          <div className="flex items-center gap-2">
            <Button onClick={() => go(-1)} aria-label="Previous week">
              ←
            </Button>
            <Button onClick={() => go(1)} disabled={!shownWeek || shownWeek >= thisWeekStart} aria-label="Next week">
              →
            </Button>
          </div>
        }
      />
      <FilterBar filters={filters} showRange={false} showBucket={false} />

      {digest.data && <Household people={filters.people} digest={digest.data.people} />}

      <div className={cx('grid gap-4 xl:grid-cols-2 transition-opacity', digest.isFetching && 'opacity-60')}>
        {filters.people.map((person) => (
          <PersonDigest key={person.id} person={person} digest={digest.data?.people[String(person.id)]} />
        ))}
      </div>

      <h2 className="mt-10 text-lg font-semibold text-ink">Patterns in the last 90 days</h2>
      <p className="mb-3 text-sm text-ink-2">
        Found in each person's own data and only shown when there are enough nights and a clear difference. They're
        associations, not proof of cause - but they're a good place to start experimenting.
      </p>
      <div className="grid gap-4 xl:grid-cols-2">
        {filters.people.map((person) => (
          <PersonInsights key={person.id} person={person} insights={insights.data?.people[String(person.id)]} loading={insights.isLoading} />
        ))}
      </div>
    </>
  )
}

function Household({ people, digest }: { people: Person[]; digest: Record<string, DigestPerson> }) {
  const units = useUnits()
  if (people.length < 2) return null
  const total = (key: string) =>
    people.reduce((sum, p) => sum + (digest[String(p.id)]?.metrics[key]?.value ?? 0), 0)
  const steps = total('steps')
  const workouts = total('workouts')
  const hours = total('workout_hours')
  if (!steps && !workouts) return null
  return (
    <p className="mb-4 rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink-2">
      <span className="font-medium text-ink">Together this week:</span>{' '}
      {formatNumber(workouts)} workout{workouts === 1 ? '' : 's'} ({formatNumber(hours, 1)} h) and {formatNumber(steps)} steps
      {steps ? ` - about ${units.distance(steps * 0.78)} on foot` : ''}.
    </p>
  )
}

function DeltaText({ metric, delta }: { metric: MetricDef; delta: number | null }) {
  if (delta === null) return null
  if (Math.abs(delta) < 3) return <span className="text-xs text-ink-2">≈ usual</span>
  const up = delta > 0
  const tone = metric.direction === 'none' ? 'neutral' : (metric.direction === 'up') === up ? 'good' : 'bad'
  return (
    <span className={cx('text-xs font-medium', tone === 'good' ? 'text-good' : tone === 'bad' ? 'text-bad' : 'text-ink-2')}>
      <span aria-hidden>{up ? '▲' : '▼'}</span> {Math.abs(delta).toFixed(Math.abs(delta) < 10 ? 1 : 0)}%
      <span className="sr-only">{tone === 'good' ? ' better than' : tone === 'bad' ? ' worse than' : ' vs'} usual</span>
    </span>
  )
}

function PersonDigest({ person, digest }: { person: Person; digest?: DigestPerson }) {
  const { byKey } = useCatalog()
  const units = useUnits()
  if (!digest) return null
  if (!digest.has_data) {
    return (
      <Card>
        <PersonKey person={person} className="text-base font-semibold text-ink" />
        <EmptyState title="No data for this week" />
      </Card>
    )
  }
  const show = (key: string, value: number | null | undefined) => {
    const metric = byKey[key]
    if (!metric || value === null || value === undefined) return '–'
    const shown = units.metric(metric)
    return shown.format(shown.isClock ? value : shown.toDisplay(value))
  }

  return (
    <Card>
      <PersonKey person={person} className="mb-3 text-base font-semibold text-ink" />
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
        {KPI_KEYS.filter((k) => digest.metrics[k]?.value !== null && digest.metrics[k] !== undefined).map((key) => {
          const metric = byKey[key]
          const entry = digest.metrics[key]
          if (!metric) return null
          const label = metric.agg === 'sum' ? `${metric.label}, week` : metric.label
          return (
            <div key={key} className="min-w-0">
              <dt className="truncate text-xs text-ink-2" title={label}>
                {label}
              </dt>
              <dd className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-lg font-semibold text-ink">{show(key, entry.value)}</span>
                <DeltaText metric={metric} delta={entry.delta_pct} />
              </dd>
              {key === 'bedtime' && entry.spread_min != null && (
                <dd className="text-xs text-ink-2">varied by ±{entry.spread_min} min</dd>
              )}
            </div>
          )
        })}
      </dl>

      {digest.highlights.length > 0 && (
        <div className="mt-4 border-t border-line pt-3">
          <h3 className="mb-1.5 text-xs font-semibold tracking-wide text-ink-2 uppercase">Highlights</h3>
          <ul className="space-y-1 text-sm text-ink">
            {digest.highlights.map((h, i) => (
              <HighlightRow key={i} highlight={h} show={show} />
            ))}
          </ul>
        </div>
      )}

      {digest.goals.length > 0 && (
        <div className="mt-4 border-t border-line pt-3">
          <h3 className="mb-1.5 text-xs font-semibold tracking-wide text-ink-2 uppercase">Goals</h3>
          <ul className="space-y-1.5 text-sm">
            {digest.goals.map((g) => {
              const metric = byKey[g.metric]
              const target = show(g.metric, g.target)
              const op = g.comparison === 'at_least' ? '≥' : '≤'
              const met = g.period === 'day' ? (g.days ? (g.met_days ?? 0) / g.days >= 0.7 : null) : g.met
              return (
                <li key={g.goal_id} className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-ink">
                    {metric?.label} {op} {target} {g.period === 'day' ? 'a day' : 'this week'}
                  </span>
                  {g.period === 'day' ? (
                    <StatusBadge status={met ? 'good' : met === null ? 'neutral' : 'warning'}>
                      {g.met_days} of {g.days} days
                    </StatusBadge>
                  ) : (
                    <StatusBadge status={g.met ? 'good' : g.met === null ? 'neutral' : 'critical'}>
                      {g.met === null ? 'No data' : g.met ? `Met · ${show(g.metric, g.value)}` : `Missed · ${show(g.metric, g.value)}`}
                    </StatusBadge>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {digest.notable.length > 0 && (
        <div className="mt-4 border-t border-line pt-3">
          <h3 className="mb-1.5 text-xs font-semibold tracking-wide text-ink-2 uppercase">Worth knowing</h3>
          <ul className="space-y-1 text-sm text-ink">
            {digest.notable.map((n) => (
              <li key={n.metric} className="flex items-center gap-2">
                <StatusBadge status={n.good ? 'good' : 'warning'}>{n.good ? 'Up' : 'Watch'}</StatusBadge>
                <span>
                  {byKey[n.metric]?.label} {n.delta_pct > 0 ? 'up' : 'down'} {Math.abs(n.delta_pct).toFixed(0)}% on usual
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  )
}

function HighlightRow({ highlight: h, show }: { highlight: Highlight; show: (key: string, v: number | null | undefined) => string }) {
  const units = useUnits()
  const day = weekday.format(parseDay(h.date))
  switch (h.kind) {
    case 'best_night':
      return <li>Best night: <span className="text-ink-2">{day}</span> - sleep score {show(h.metric, h.value)}</li>
    case 'worst_night':
      return <li>Toughest night: <span className="text-ink-2">{day}</span> - sleep score {show(h.metric, h.value)}</li>
    case 'most_active_day':
      return <li>Most active day: <span className="text-ink-2">{day}</span> - {show(h.metric, h.value)} steps</li>
    case 'biggest_workout':
      return (
        <li>
          Biggest workout:{' '}
          <Link to={`/workouts/${h.activity_id}`} className="font-medium underline-offset-2 hover:underline">
            {h.name ?? SPORT_LABELS[h.sport]}
          </Link>{' '}
          <span className="text-ink-2">
            {day} · {h.distance_m ? `${units.distance(h.distance_m)} · ` : ''}
            {formatDuration(h.duration_s)}
          </span>
        </li>
      )
    case 'personal_record':
      return (
        <li>
          Personal record:{' '}
          <Link to={`/workouts/${h.activity_id}`} className="font-medium underline-offset-2 hover:underline">
            {h.name ?? SPORT_LABELS[h.sport]}
          </Link>{' '}
          <span className="text-ink-2">{day}</span>
        </li>
      )
  }
}

function PersonInsights({ person, insights, loading }: { person: Person; insights?: Insight[]; loading: boolean }) {
  return (
    <Card>
      <PersonKey person={person} className="mb-3 text-base font-semibold text-ink" />
      {loading ? (
        <p className="text-sm text-ink-2">Looking for patterns…</p>
      ) : !insights?.length ? (
        <EmptyState title="No clear patterns yet">
          Insights need a few weeks of nights with and without each factor. Check back as more data syncs.
        </EmptyState>
      ) : (
        <ul className="space-y-4">
          {insights.map((insight) => (
            <InsightRow key={insight.id} insight={insight} person={person} />
          ))}
        </ul>
      )}
    </Card>
  )
}

function InsightRow({ insight, person }: { insight: Insight; person: Person }) {
  const { byKey } = useCatalog()
  const units = useUnits()
  const palette = usePalette()
  const color = palette.series(person.color_slot)
  const show = (key: string, v: number) => {
    const metric = byKey[key]
    if (!metric) return formatNumber(v, 1)
    const shown = units.metric(metric)
    return shown.format(shown.isClock ? v : shown.toDisplay(v))
  }

  if (insight.kind === 'groups') {
    const [a, b] = insight.groups
    const max = Math.max(a.mean, b.mean) || 1
    const metric = byKey[insight.outcome]
    const isClock = metric?.unit === 'clock'
    return (
      <li className="border-t border-line pt-3 first:border-0 first:pt-0">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-sm font-medium text-ink">{insight.title}</h3>
          <span className="text-xs text-ink-2">
            {insight.strength} difference
            {insight.favourable !== null && <> · {insight.favourable ? 'in your favour' : 'worth watching'}</>}
          </span>
        </div>
        <div className="mt-2 space-y-1.5 text-xs">
          {[a, b].map((g, i) => (
            <div key={g.label} className="grid grid-cols-[8.5rem_minmax(0,1fr)_5.5rem] items-center gap-2">
              <span className="truncate text-ink-2">{g.label}</span>
              {isClock ? (
                <span />
              ) : (
                <span className="h-2.5 rounded-r" style={{ width: `${(g.mean / max) * 100}%`, background: i === 0 ? color : palette.chrome.deemph }} />
              )}
              <span className="text-right text-ink tabular">
                <span className="font-semibold">{show(insight.outcome, g.mean)}</span>{' '}
                <span className="text-ink-2">({g.n})</span>
              </span>
            </div>
          ))}
        </div>
      </li>
    )
  }

  const xMetric = byKey[insight.x]
  const yMetric = byKey[insight.y]
  const points = insight.points.map(([x, y]) => ({ x, y }))
  return (
    <li className="border-t border-line pt-3 first:border-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-medium text-ink">{insight.title}</h3>
        <span className="text-xs text-ink-2">
          {insight.strength} link · r = {insight.r.toFixed(2)} · {insight.n} days
        </span>
      </div>
      <p className="mt-0.5 text-xs text-ink-2">{insight.summary}</p>
      <div className="mt-2">
        <ResponsiveContainer width="100%" height={150}>
          <ScatterChart margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={palette.chrome.grid} />
            <XAxis
              type="number"
              dataKey="x"
              domain={['auto', 'auto']}
              tickLine={false}
              axisLine={{ stroke: palette.chrome.axis }}
              tickFormatter={(v: number) => show(insight.x, v)}
              name={xMetric?.label}
            />
            <YAxis type="number" dataKey="y" domain={['auto', 'auto']} width={44} tickLine={false} axisLine={false} tickFormatter={(v: number) => show(insight.y, v)} name={yMetric?.label} />
            <Tooltip
              cursor={{ stroke: palette.chrome.axis }}
              isAnimationActive={false}
              content={({ active, payload }) =>
                active && payload?.length ? (
                  <div className="rounded-lg border border-line bg-raised px-3 py-2 text-xs shadow-lg">
                    <p>
                      <span className="font-semibold text-ink">{show(insight.x, payload[0].payload.x)}</span> <span className="text-ink-2">{xMetric?.label}</span>
                    </p>
                    <p>
                      <span className="font-semibold text-ink">{show(insight.y, payload[0].payload.y)}</span> <span className="text-ink-2">{yMetric?.label}</span>
                    </p>
                  </div>
                ) : null
              }
            />
            <Scatter data={points} fill={color} fillOpacity={0.7} stroke={palette.chrome.surface} strokeWidth={1} isAnimationActive={false} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </li>
  )
}
