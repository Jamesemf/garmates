import { RANGE_PRESETS, type Filters } from '../lib/hooks'
import { usePalette } from '../lib/theme'
import { cx, inputClass } from './ui'

/** The one filter row: date range first, then people, then granularity. Scopes every chart below. */
export function FilterBar({
  filters,
  showBucket = true,
  showRange = true,
}: {
  filters: Filters
  showBucket?: boolean
  showRange?: boolean
}) {
  const palette = usePalette()
  const togglePerson = (id: number) => {
    const current = filters.peopleIds
    const next = current.includes(id) ? current.filter((x) => x !== id) : [...current, id]
    if (next.length === 0) return // keep at least one person selected
    filters.set({ people: next.join(',') })
  }

  return (
    <div className="mb-5 flex flex-wrap items-center gap-2">
      {showRange && (
        <>
          <label className="sr-only" htmlFor="range">
            Date range
          </label>
          <select
            id="range"
            value={filters.range}
            onChange={(e) => {
              const value = e.target.value
              filters.set(value === 'custom' ? { range: value, start: filters.start, end: filters.end } : { range: value, start: null, end: null })
            }}
            className="rounded-lg border border-line bg-raised px-2.5 py-1.5 text-sm text-ink"
          >
            {RANGE_PRESETS.map((p) => (
              <option key={p.key} value={p.key}>
                {p.label}
              </option>
            ))}
            <option value="custom">Custom range…</option>
          </select>
          {filters.range === 'custom' && (
            <span className="flex items-center gap-1.5 text-sm text-ink-2">
              <input
                type="date"
                aria-label="Start date"
                value={filters.start}
                max={filters.end}
                onChange={(e) => e.target.value && filters.set({ start: e.target.value })}
                className={cx(inputClass, 'w-auto py-1.5')}
              />
              –
              <input
                type="date"
                aria-label="End date"
                value={filters.end}
                min={filters.start}
                onChange={(e) => e.target.value && filters.set({ end: e.target.value })}
                className={cx(inputClass, 'w-auto py-1.5')}
              />
            </span>
          )}
        </>
      )}

      {filters.allPeople.length > 1 && (
        <div role="group" aria-label="People" className="flex flex-wrap items-center gap-1.5">
          {filters.allPeople.map((person) => {
            const on = filters.peopleIds.includes(person.id)
            return (
              <button
                key={person.id}
                type="button"
                aria-pressed={on}
                onClick={() => togglePerson(person.id)}
                className={cx(
                  'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-sm transition',
                  on ? 'border-line bg-raised text-ink' : 'border-dashed border-line text-muted hover:text-ink-2',
                )}
              >
                <span
                  aria-hidden
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ background: on ? palette.series(person.color_slot) : 'transparent', boxShadow: on ? undefined : `inset 0 0 0 1.5px ${palette.series(person.color_slot)}` }}
                />
                {person.name}
              </button>
            )
          })}
        </div>
      )}

      {showBucket && (
        <>
          <label className="sr-only" htmlFor="bucket">
            Granularity
          </label>
          <select
            id="bucket"
            value={filters.bucketChoice}
            onChange={(e) => filters.set({ bucket: e.target.value === 'auto' ? null : e.target.value })}
            className="ml-auto rounded-lg border border-line bg-raised px-2.5 py-1.5 text-sm text-ink"
          >
            <option value="auto">Auto ({filters.bucket === 'day' ? 'daily' : `${filters.bucket}ly`})</option>
            <option value="day">Daily</option>
            <option value="week">Weekly</option>
            <option value="month">Monthly</option>
          </select>
        </>
      )}
    </div>
  )
}
