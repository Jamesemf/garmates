import { useState, type FormEvent } from 'react'
import { ChartCard, PeopleLegend, PeopleLineChart, PeopleTable } from '../components/charts'
import { FilterBar } from '../components/FilterBar'
import { Button, Card, cx, EmptyState, ErrorNote, Field, inputClass, PageHeader, PersonKey, StatusBadge } from '../components/ui'
import { api } from '../lib/api'
import { addDays, formatDay, formatLongDay, formatNumber, parseDay, toIsoDay } from '../lib/format'
import { useCatalog, useChallenges, useFilters, useGoalMutation, useGoals } from '../lib/hooks'
import { usePalette } from '../lib/theme'
import type { Challenge, Goal, GoalStatus, MetricDef, Period, Person, Scoring } from '../lib/types'
import { usePrefs, useUnits, type DisplayMetric } from '../lib/units'

const PERIOD_WORD: Record<Period, string> = { day: 'day', week: 'week', month: 'month' }

const STATUS: Record<GoalStatus, { badge: 'good' | 'warning' | 'critical' | 'neutral'; label: string }> = {
  met: { badge: 'good', label: 'Met' },
  on_track: { badge: 'good', label: 'On track' },
  in_progress: { badge: 'neutral', label: 'In progress' },
  behind: { badge: 'warning', label: 'Behind' },
  missed: { badge: 'critical', label: 'Missed' },
  no_data: { badge: 'neutral', label: 'No data yet' },
}

export function GoalsPage() {
  const filters = useFilters()
  const goals = useGoals(filters.people)
  const challenges = useChallenges()

  return (
    <>
      <PageHeader title="Goals & challenges" subtitle="Personal targets with streaks, plus head-to-head challenges." />
      <FilterBar filters={filters} showRange={false} showBucket={false} />

      <div className="grid gap-4 xl:grid-cols-2">
        {filters.people.map((person) => (
          <PersonGoals key={person.id} person={person} goals={(goals.data?.goals ?? []).filter((g) => g.person_id === person.id)} />
        ))}
      </div>

      <div className="mt-10 mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-ink">Challenges</h2>
          <p className="text-sm text-ink-2">Score by total, by daily average, or by improvement on your own usual - the fair way to compete across different baselines.</p>
        </div>
      </div>
      <NewChallenge people={filters.allPeople} />
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        {(challenges.data?.challenges ?? []).map((c) => (
          <ChallengeCard key={c.id} challenge={c} people={filters.allPeople} />
        ))}
      </div>
      {challenges.data && challenges.data.challenges.length === 0 && (
        <p className="mt-3 text-sm text-ink-2">No challenges yet.</p>
      )}
    </>
  )
}

// --- goals ---------------------------------------------------------------------------------

function goalTitle(goal: Pick<Goal, 'comparison' | 'target' | 'period'>, metric: MetricDef, shown: DisplayMetric): string {
  const op = shown.isClock
    ? goal.comparison === 'at_least' ? 'no earlier than' : 'no later than'
    : goal.comparison === 'at_least' ? '≥' : '≤'
  const target = shown.format(shown.isClock ? goal.target : shown.toDisplay(goal.target))
  const kind =
    metric.agg === 'sum'
      ? `a ${PERIOD_WORD[goal.period]}`
      : goal.period === 'day'
        ? 'each day'
        : `on average each ${PERIOD_WORD[goal.period]}`
  return `${metric.label} ${op} ${target} ${kind}`
}

function PersonGoals({ person, goals }: { person: Person; goals: Goal[] }) {
  const [adding, setAdding] = useState(false)
  return (
    <Card>
      <div className="mb-3 flex items-center justify-between gap-2">
        <PersonKey person={person} className="text-base font-semibold text-ink" />
        {person.can_manage && !adding && (
          <Button onClick={() => setAdding(true)}>Add goal</Button>
        )}
      </div>
      {adding && <AddGoal person={person} onDone={() => setAdding(false)} />}
      {goals.length === 0 && !adding ? (
        <EmptyState title={person.can_manage ? 'No goals yet' : 'No shared goals'}>
          {person.can_manage ? 'Pick a target - steps, sleep, workouts, bedtime - and the dashboard tracks streaks for you.' : null}
        </EmptyState>
      ) : (
        <ul className="divide-y divide-line">
          {goals.map((goal) => (
            <GoalRow key={goal.id} goal={goal} person={person} />
          ))}
        </ul>
      )}
    </Card>
  )
}

function GoalRow({ goal, person }: { goal: Goal; person: Person }) {
  const palette = usePalette()
  const units = useUnits()
  const { byKey } = useCatalog()
  const remove = useGoalMutation(() => api.del(`/api/goals/${goal.id}`))
  const metric = byKey[goal.metric_key]
  if (!metric) return null
  const shown = units.metric(metric)
  const color = palette.series(person.color_slot)
  const { current } = goal
  const display = (v: number | null) => (v === null ? '–' : shown.format(shown.isClock ? v : shown.toDisplay(v)))
  // Meter only for totals and levels with a natural zero; clock goals show the value instead.
  const ratio = current.value === null || shown.isClock || goal.target <= 0 ? null : Math.min(1, current.value / goal.target)
  const status = STATUS[current.status]
  const periodUnit = goal.period === 'day' ? 'days' : `${goal.period}s`

  return (
    <li className="py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink">{goalTitle(goal, metric, shown)}</p>
          <p className="mt-0.5 text-xs text-ink-2">
            {goal.period === 'day' ? 'Today' : goal.period === 'week' ? 'This week' : 'This month'}:{' '}
            <span className="font-semibold text-ink tabular">{display(current.value)}</span>
            {!shown.isClock && <> of {display(goal.target)}</>}
            {goal.period !== 'day' && ` · day ${current.elapsed_days} of ${current.total_days}`}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <StatusBadge status={status.badge}>{status.label}</StatusBadge>
          {person.can_manage && (
            <button
              type="button"
              aria-label="Delete goal"
              title="Delete goal"
              onClick={() => window.confirm('Delete this goal?') && remove.mutate(undefined)}
              className="rounded px-1.5 text-muted hover:bg-wash hover:text-ink"
            >
              ×
            </button>
          )}
        </div>
      </div>
      {ratio !== null && (
        <div
          className="mt-2 h-2 w-full overflow-hidden rounded-full"
          style={{ background: `color-mix(in srgb, ${color} 18%, transparent)` }}
          role="meter"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(ratio * 100)}
          aria-label="Progress towards goal"
        >
          <div className="h-full rounded-full" style={{ width: `${ratio * 100}%`, background: color }} />
        </div>
      )}
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-ink-2">
        <HistoryStrip goal={goal} color={color} display={display} />
        <span>
          Streak <span className="font-semibold text-ink">{goal.streak}</span> {goal.streak === 1 ? periodUnit.slice(0, -1) : periodUnit}
          {goal.hit_rate !== null && <> · hit {Math.round(goal.hit_rate * 100)}% of the last {goal.history.length} {periodUnit}</>}
        </span>
      </div>
    </li>
  )
}

/** One mark per past period: filled = met, hollow = missed, dot = no data (shape, not just colour). */
function HistoryStrip({ goal, color, display }: { goal: Goal; color: string; display: (v: number | null) => string }) {
  const last = goal.history.slice(-(goal.period === 'day' ? 28 : 12))
  return (
    <ol className="flex items-center gap-[3px]" aria-label="Recent periods">
      {last.map((h) => {
        const label = `${goal.period === 'week' ? 'Week of ' : ''}${formatDay(h.start, goal.period === 'month' ? 'month' : 'day')}: ${
          h.met === null ? 'no data' : `${display(h.value)} - ${h.met ? 'met' : 'missed'}`
        }`
        return (
          <li key={h.start} title={label} aria-label={label} className="flex h-3 w-3 items-center justify-center">
            {h.met === null ? (
              <span className="h-1 w-1 rounded-full bg-axis" />
            ) : (
              <span
                className="h-2.5 w-2.5 rounded-sm"
                style={h.met ? { background: color } : { boxShadow: `inset 0 0 0 1.5px ${color}`, opacity: 0.7 }}
              />
            )}
          </li>
        )
      })}
    </ol>
  )
}

const GOAL_PRESETS: { label: string; metric: string; comparison: 'at_least' | 'at_most'; target: number; period: Period }[] = [
  { label: '10k steps a day', metric: 'steps', comparison: 'at_least', target: 10000, period: 'day' },
  { label: '3 workouts a week', metric: 'workouts', comparison: 'at_least', target: 3, period: 'week' },
  { label: '150 intensity min a week', metric: 'intensity_minutes', comparison: 'at_least', target: 150, period: 'week' },
  { label: '7.5 h sleep on average', metric: 'sleep_hours', comparison: 'at_least', target: 7.5, period: 'week' },
  { label: 'In bed by 23:00 on average', metric: 'bedtime', comparison: 'at_most', target: 23, period: 'week' },
]

function hoursFromTime(value: string, metricKey: string): number {
  const [h, m] = value.split(':').map(Number)
  const hours = h + m / 60
  // Bedtimes count from the evening's midnight, so 00:30 is 24.5.
  return metricKey === 'bedtime' && hours < 12 ? hours + 24 : hours
}

function timeFromHours(hours: number): string {
  const minutes = Math.round((hours % 24) * 60)
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`
}

function AddGoal({ person, onDone }: { person: Person; onDone: () => void }) {
  const { data: catalog, byKey } = useCatalog()
  const units = useUnits()
  const [metricKey, setMetricKey] = useState('steps')
  const [comparison, setComparison] = useState<'at_least' | 'at_most'>('at_least')
  const [target, setTarget] = useState('10000')
  const [period, setPeriod] = useState<Period>('day')
  const create = useGoalMutation((body: object) => api.post('/api/goals', body))
  const metric = byKey[metricKey]
  const shown = metric ? units.metric(metric) : null

  const choose = (key: string) => {
    setMetricKey(key)
    const m = byKey[key]
    if (!m) return
    setComparison(m.direction === 'down' ? 'at_most' : 'at_least')
    setTarget(m.unit === 'clock' ? (key === 'bedtime' ? '23:00' : '07:00') : '')
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!shown) return
    const value = shown.isClock ? hoursFromTime(target, metricKey) : shown.fromDisplay(Number(target))
    await create
      .mutateAsync({ person_id: person.id, metric_key: metricKey, comparison, target: value, period })
      .then(onDone, () => undefined)
  }

  return (
    <form onSubmit={submit} className="mb-4 space-y-3 rounded-lg border border-line bg-raised p-3">
      <div className="flex flex-wrap gap-1.5">
        {GOAL_PRESETS.map((p) => (
          <button
            key={p.label}
            type="button"
            onClick={() => {
              setMetricKey(p.metric)
              setComparison(p.comparison)
              setPeriod(p.period)
              setTarget(byKey[p.metric]?.unit === 'clock' ? timeFromHours(p.target) : String(p.target))
            }}
            className="rounded-full border border-line px-2.5 py-1 text-xs text-ink-2 hover:bg-wash hover:text-ink"
          >
            {p.label}
          </button>
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-4">
        <Field label="Metric">
          <select className={inputClass} value={metricKey} onChange={(e) => choose(e.target.value)}>
            {catalog?.categories
              .filter((c) => person.visible_categories.includes(c.key))
              .map((c) => (
                <optgroup key={c.key} label={c.label}>
                  {catalog.metrics
                    .filter((m) => m.category === c.key && m.key !== 'step_goal')
                    .map((m) => (
                      <option key={m.key} value={m.key}>
                        {m.label}
                      </option>
                    ))}
                </optgroup>
              ))}
          </select>
        </Field>
        <Field label="Goal">
          <select className={inputClass} value={comparison} onChange={(e) => setComparison(e.target.value as 'at_least' | 'at_most')}>
            <option value="at_least">{shown?.isClock ? 'At or after' : 'At least'}</option>
            <option value="at_most">{shown?.isClock ? 'No later than' : 'At most'}</option>
          </select>
        </Field>
        <Field label={`Target${shown?.def.unit ? ` (${shown.def.unit})` : ''}`}>
          {shown?.isClock ? (
            <input type="time" className={inputClass} value={target} onChange={(e) => setTarget(e.target.value)} required />
          ) : (
            <input type="number" min={0} step="any" className={inputClass} value={target} onChange={(e) => setTarget(e.target.value)} required />
          )}
        </Field>
        <Field label={metric?.agg === 'sum' ? 'Total per' : 'Average over'}>
          <select className={inputClass} value={period} onChange={(e) => setPeriod(e.target.value as Period)}>
            <option value="day">Day</option>
            <option value="week">Week</option>
            <option value="month">Month</option>
          </select>
        </Field>
      </div>
      <ErrorNote error={create.error} />
      <div className="flex gap-2">
        <Button type="submit" variant="primary" disabled={create.isPending}>
          Save goal
        </Button>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

// --- challenges ----------------------------------------------------------------------------

function scoreText(challenge: Challenge, metric: MetricDef | undefined, shown: DisplayMetric | null, score: number | null): string {
  if (score === null || !metric || !shown) return '–'
  if (challenge.scoring === 'improvement') return `${score > 0 ? '+' : ''}${formatNumber(score, 1)}% vs usual`
  return shown.format(shown.isClock ? score : shown.toDisplay(score))
}

function ChallengeCard({ challenge, people }: { challenge: Challenge; people: Person[] }) {
  const { byKey } = useCatalog()
  const units = useUnits()
  const remove = useGoalMutation(() => api.del(`/api/challenges/${challenge.id}`))
  const metric = byKey[challenge.metric_key]
  const shown = metric ? units.metric(metric) : null
  const byId = new Map(people.map((p) => [p.id, p]))
  const visible = challenge.entries.filter((e) => !e.hidden).map((e) => byId.get(e.person_id)).filter((p): p is Person => !!p)
  const me = people.find((p) => p.is_me)
  const scoringText = { total: 'Total', average: 'Daily average', improvement: 'Improvement vs own usual' }[challenge.scoring]
  const statusBadge =
    challenge.status === 'active' ? (
      <StatusBadge status="running">{challenge.days_left} day{challenge.days_left === 1 ? '' : 's'} left</StatusBadge>
    ) : challenge.status === 'upcoming' ? (
      <StatusBadge status="neutral">Starts {formatLongDay(challenge.start)}</StatusBadge>
    ) : (
      <StatusBadge status="good">Finished</StatusBadge>
    )
  const format = (v: number | null) => scoreText(challenge, metric, shown, v)
  // Race rows are converted to display units up front, so the chart/table format them as-is.
  const chartFormat = (v: number | null) =>
    v === null ? '–' : challenge.scoring === 'improvement' ? `${v > 0 ? '+' : ''}${formatNumber(v, 1)}%` : shown ? shown.format(v) : formatNumber(v)
  const rows = challenge.race.map((r) => {
    const row: { date: string } & Record<string, number | string> = { date: r.date }
    for (const [k, v] of Object.entries(r)) {
      if (k !== 'date' && typeof v === 'number') row[k] = challenge.scoring === 'improvement' || shown?.isClock ? v : (shown?.toDisplay(v) ?? v)
    }
    return row
  })

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-ink">{challenge.name}</h3>
          <p className="mt-0.5 text-xs text-ink-2">
            {metric?.label} · {scoringText} · {formatLongDay(challenge.start)} – {formatLongDay(challenge.end)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {statusBadge}
          {(challenge.created_by === me?.id || me?.is_admin) && (
            <button
              type="button"
              aria-label="Delete challenge"
              title="Delete challenge"
              onClick={() => window.confirm(`Delete "${challenge.name}"?`) && remove.mutate(undefined)}
              className="rounded px-1.5 text-muted hover:bg-wash hover:text-ink"
            >
              ×
            </button>
          )}
        </div>
      </div>

      <ol className="mt-3 space-y-1.5">
        {challenge.entries.map((entry) => {
          const person = byId.get(entry.person_id)
          if (!person) return null
          const winner = challenge.status === 'finished' && entry.rank === 1
          return (
            <li key={entry.person_id} className="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-2 text-sm">
              <span className="text-right text-ink-2 tabular">{entry.rank ?? '–'}</span>
              <span className="flex min-w-0 items-center gap-2">
                <PersonKey person={person} className="text-ink" />
                {winner && <span className="rounded border border-line px-1 text-[10px] font-semibold tracking-wide text-ink-2 uppercase">Winner</span>}
              </span>
              <span className={cx('text-right tabular', entry.hidden ? 'text-muted' : 'font-semibold text-ink')}>
                {entry.hidden ? 'Not shared' : format(entry.score)}
              </span>
            </li>
          )
        })}
      </ol>

      {rows.length > 1 && visible.length > 0 && (
        <ChartCard
          title={challenge.scoring === 'total' ? 'Running total' : challenge.scoring === 'average' ? 'Running average' : 'Improvement so far'}
          className="mt-4 border-0 !p-0"
          legend={<PeopleLegend people={visible} />}
          table={<PeopleTable rows={rows} people={visible} bucket="day" format={chartFormat} />}
        >
          <PeopleLineChart
            rows={rows}
            people={visible}
            height={180}
            format={chartFormat}
            referenceY={challenge.scoring === 'improvement' ? 0 : undefined}
            yFormat={shown?.isClock ? (v) => shown.format(v) : undefined}
          />
        </ChartCard>
      )}
      <ErrorNote error={remove.error} />
    </Card>
  )
}

function NewChallenge({ people }: { people: Person[] }) {
  const { data: catalog, byKey } = useCatalog()
  const prefs = usePrefs()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [metricKey, setMetricKey] = useState('steps')
  const [scoring, setScoring] = useState<Scoring>('total')
  const [range, setRange] = useState<'this_week' | 'next_7' | 'this_month' | 'custom'>('next_7')
  const [start, setStart] = useState(toIsoDay(new Date()))
  const [end, setEnd] = useState(addDays(toIsoDay(new Date()), 6))
  const metric = byKey[metricKey]
  const eligible = people.filter((p) => metric && p.visible_categories.includes(metric.category))
  const [participants, setParticipants] = useState<number[]>([])
  const create = useGoalMutation((body: object) => api.post('/api/challenges', body))

  const dates = (): [string, string] => {
    const today = toIsoDay(new Date())
    if (range === 'next_7') return [today, addDays(today, 6)]
    if (range === 'this_week') {
      const d = parseDay(today)
      const offset = prefs.week_start === 'sunday' ? d.getDay() : (d.getDay() + 6) % 7
      const first = addDays(today, -offset)
      return [first, addDays(first, 6)]
    }
    if (range === 'this_month') {
      const d = parseDay(today)
      return [toIsoDay(new Date(d.getFullYear(), d.getMonth(), 1)), toIsoDay(new Date(d.getFullYear(), d.getMonth() + 1, 0))]
    }
    return [start, end]
  }

  const choose = (key: string) => {
    setMetricKey(key)
    const m = byKey[key]
    if (m && m.agg !== 'sum' && scoring === 'total') setScoring('average')
  }

  if (!open) {
    return (
      <Button variant="primary" onClick={() => setOpen(true)}>
        New challenge
      </Button>
    )
  }
  const chosen = participants.length ? participants : eligible.map((p) => p.id)
  return (
    <Card>
      <form
        className="space-y-3"
        onSubmit={async (e) => {
          e.preventDefault()
          const [s, en] = dates()
          await create
            .mutateAsync({
              name: name || `${metric?.label ?? 'Challenge'} ${scoring === 'improvement' ? 'improvement ' : ''}challenge`,
              metric_key: metricKey,
              scoring,
              start_date: s,
              end_date: en,
              participant_ids: chosen,
            })
            .then(() => setOpen(false), () => undefined)
        }}
      >
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Name">
            <input className={inputClass} value={name} placeholder="e.g. November step-off" onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Metric">
            <select className={inputClass} value={metricKey} onChange={(e) => choose(e.target.value)}>
              {catalog?.categories.map((c) => (
                <optgroup key={c.key} label={c.label}>
                  {catalog.metrics
                    .filter((m) => m.category === c.key && m.direction !== 'none')
                    .map((m) => (
                      <option key={m.key} value={m.key}>
                        {m.label}
                      </option>
                    ))}
                </optgroup>
              ))}
            </select>
          </Field>
          <Field label="Scoring" hint={scoring === 'improvement' ? "Compares each person's challenge average with their own previous 30 days." : undefined}>
            <select className={inputClass} value={scoring} onChange={(e) => setScoring(e.target.value as Scoring)}>
              {metric?.agg === 'sum' && <option value="total">Total</option>}
              <option value="average">Daily average</option>
              <option value="improvement">Improvement vs own usual</option>
            </select>
          </Field>
          <Field label="When">
            <select className={inputClass} value={range} onChange={(e) => setRange(e.target.value as typeof range)}>
              <option value="next_7">Next 7 days</option>
              <option value="this_week">This week</option>
              <option value="this_month">This month</option>
              <option value="custom">Custom…</option>
            </select>
          </Field>
          {range === 'custom' && (
            <>
              <Field label="Start">
                <input type="date" className={inputClass} value={start} onChange={(e) => setStart(e.target.value)} />
              </Field>
              <Field label="End">
                <input type="date" className={inputClass} value={end} min={start} onChange={(e) => setEnd(e.target.value)} />
              </Field>
            </>
          )}
        </div>
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium text-ink">Who's in</legend>
          <div className="flex flex-wrap gap-3">
            {eligible.map((p) => (
              <label key={p.id} className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-[var(--text-primary)]"
                  checked={chosen.includes(p.id)}
                  onChange={() => setParticipants(chosen.includes(p.id) ? chosen.filter((x) => x !== p.id) : [...chosen, p.id])}
                />
                <PersonKey person={p} />
              </label>
            ))}
          </div>
          {eligible.length < people.length && (
            <p className="mt-1 text-xs text-ink-2">People who don't share this kind of data with you can't be added.</p>
          )}
        </fieldset>
        <ErrorNote error={create.error} />
        <div className="flex gap-2">
          <Button type="submit" variant="primary" disabled={create.isPending || chosen.length < 2}>
            Start challenge
          </Button>
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  )
}
