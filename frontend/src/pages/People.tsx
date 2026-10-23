import { useState, type FormEvent } from 'react'
import { Button, Card, cx, ErrorNote, Field, inputClass, PageHeader, StatusBadge } from '../components/ui'
import { api } from '../lib/api'
import { addDays, formatLongDay, formatRelative, toIsoDay } from '../lib/format'
import { useCatalog, usePeople, usePeopleMutation, useRefreshAll, useSyncState } from '../lib/hooks'
import { usePalette } from '../lib/theme'
import type { Category, Person } from '../lib/types'

const KEY_PAGE = 'https://connect.garmin.com/app/settings/personalApiToken'

const EXPIRY_OPTIONS = [
  { value: '', label: "I don't know" },
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
  { value: '180', label: '6 months' },
  { value: '365', label: '1 year' },
]

export function PeoplePage({ me }: { me: Person }) {
  const { data: people = [], isLoading } = usePeople()
  const hasDemo = people.some((p) => p.is_demo)
  const refreshAll = useRefreshAll()
  const demo = usePeopleMutation(async (load: boolean) => {
    await (load ? api.post('/api/demo') : api.del('/api/demo'))
    await refreshAll()
  })

  return (
    <>
      <PageHeader
        title="People & keys"
        subtitle="Each person connects their own Garmin account with a Personal API key and decides what the household can see."
        actions={
          me.is_admin && (
            <Button onClick={() => demo.mutate(!hasDemo)} disabled={demo.isPending}>
              {hasDemo ? 'Remove demo profiles' : 'Load demo profiles'}
            </Button>
          )
        }
      />
      <ErrorNote error={demo.error} />
      <KeyHelp />
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        {!isLoading && people.map((person) => <PersonCard key={person.id} person={person} me={me} />)}
      </div>
      {me.is_admin && <AddPerson />}
    </>
  )
}

function KeyHelp() {
  return (
    <details className="rounded-xl border border-line bg-surface p-4 text-sm text-ink-2">
      <summary className="cursor-pointer font-medium text-ink">How to get a Garmin Personal API key</summary>
      <ol className="mt-3 list-decimal space-y-1.5 pl-5">
        <li>
          Sign in to Garmin Connect on the web and open{' '}
          <a href={KEY_PAGE} target="_blank" rel="noreferrer noopener" className="font-medium text-ink underline underline-offset-2">
            Settings → Personal API Token
          </a>
          .
        </li>
        <li>Accept Garmin's terms, choose how long the key should last (up to a year), and create it.</li>
        <li>
          Copy the key straight away - Garmin only shows it once - and paste it into your card below. It is
          encrypted before it's stored and never shown again.
        </li>
        <li>Each person creates a key for their own account. Keys can't be renewed, so you'll make a new one when it expires.</li>
      </ol>
    </details>
  )
}

function PersonCard({ person, me }: { person: Person; me: Person }) {
  const palette = usePalette()
  const { data: catalog } = useCatalog()
  const update = usePeopleMutation((body: Record<string, unknown>) => api.patch(`/api/people/${person.id}`, body))
  const sync = usePeopleMutation(() => api.post(`/api/people/${person.id}/sync`))
  const remove = usePeopleMutation(() => api.del(`/api/people/${person.id}`))
  const [showDetails, setShowDetails] = useState(false)

  const toggleCategory = (category: Category) => {
    const current = person.shared_categories
    const next = current.includes(category) ? current.filter((c) => c !== category) : [...current, category]
    update.mutate({ shared_categories: next })
  }

  const syncStatus = person.syncing
    ? { status: 'running' as const, label: 'Syncing now' }
    : person.last_sync?.status === 'ok'
      ? { status: 'good' as const, label: `Synced ${formatRelative(person.last_sync.finished_at)}` }
      : person.last_sync?.status === 'partial'
        ? { status: 'warning' as const, label: `Partly synced ${formatRelative(person.last_sync.finished_at)}` }
        : person.last_sync?.status === 'error'
          ? { status: 'critical' as const, label: 'Last sync failed' }
          : { status: 'neutral' as const, label: 'Not synced yet' }

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-base font-semibold text-ink">
            <span aria-hidden className="inline-block h-3 w-3 rounded-full" style={{ background: palette.series(person.color_slot) }} />
            {person.name}
          </h2>
          <p className="mt-0.5 text-xs text-ink-2">
            {[person.is_me && 'You', person.is_admin && 'Admin', person.is_demo && 'Demo profile (synthetic data)', person.username && `Signs in as ${person.username}`, !person.has_login && !person.is_demo && 'No login - managed by an admin']
              .filter(Boolean)
              .join(' · ')}
          </p>
        </div>
        {person.can_manage && (
          <div role="radiogroup" aria-label="Colour" className="flex gap-1">
            {Array.from({ length: 8 }, (_, slot) => (
              <button
                key={slot}
                type="button"
                role="radio"
                aria-checked={person.color_slot === slot}
                aria-label={`Colour ${slot + 1}`}
                onClick={() => update.mutate({ color_slot: slot })}
                className={cx('h-5 w-5 rounded-full ring-offset-2 ring-offset-[var(--surface)]', person.color_slot === slot && 'ring-2 ring-[var(--text-primary)]')}
                style={{ background: palette.series(slot) }}
              />
            ))}
          </div>
        )}
      </div>

      {!person.is_demo && (
        <div className="mt-4 border-t border-line pt-4">
          <h3 className="mb-2 text-sm font-semibold text-ink">Garmin connection</h3>
          {person.key ? (
            <div className="space-y-1 text-sm">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <StatusBadge status={person.key.status === 'ok' ? 'good' : person.key.status === 'invalid' ? 'critical' : 'neutral'}>
                  {person.key.status === 'ok' ? 'Key working' : person.key.status === 'invalid' ? 'Key rejected' : 'Not verified'}
                </StatusBadge>
                {person.key.hint && <span className="text-ink-2 tabular">Key {person.key.hint}</span>}
                {person.key.garmin_display_name && <span className="text-ink-2">Garmin account: {person.key.garmin_display_name}</span>}
              </div>
              {person.key.expires_on && (
                <p className={cx('text-xs', person.key.expiring_soon ? 'text-warn' : 'text-ink-2')}>
                  {person.key.expiring_soon && <span aria-hidden>! </span>}
                  Expires {formatLongDay(person.key.expires_on)} ({person.key.days_left} days)
                </p>
              )}
              {person.key.last_error && <p className="text-xs text-bad">{person.key.last_error}</p>}
            </div>
          ) : (
            <p className="text-sm text-ink-2">No Garmin key yet.</p>
          )}
          {person.can_manage && <KeyForm person={person} />}
        </div>
      )}

      {(person.key || person.is_demo) && (
        <div className="mt-4 border-t border-line pt-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <StatusBadge status={syncStatus.status}>{syncStatus.label}</StatusBadge>
            {person.can_manage && !person.is_demo && (
              <div className="flex gap-2">
                <Button variant="ghost" onClick={() => setShowDetails((v) => !v)} aria-expanded={showDetails}>
                  {showDetails ? 'Hide details' : 'Details'}
                </Button>
                <Button onClick={() => sync.mutate(undefined)} disabled={person.syncing || sync.isPending}>
                  Sync now
                </Button>
              </div>
            )}
          </div>
          {person.last_sync?.message && person.can_manage && (
            <p className="mt-2 text-xs whitespace-pre-line text-ink-2">{person.last_sync.message}</p>
          )}
          {showDetails && <SyncDetails person={person} />}
        </div>
      )}

      <div className="mt-4 border-t border-line pt-4">
        <h3 className="mb-1 text-sm font-semibold text-ink">Shared with the household</h3>
        <p className="mb-2 text-xs text-ink-2">
          {person.is_me ? 'You always see all of your own data. ' : ''}
          Unticked categories are hidden from everyone else, including admins.
        </p>
        <div className="flex flex-wrap gap-x-4 gap-y-2">
          {catalog?.categories.map((c) => (
            <label key={c.key} className="flex items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                checked={person.shared_categories.includes(c.key)}
                disabled={!person.can_manage || update.isPending}
                onChange={() => toggleCategory(c.key)}
                className="h-4 w-4 accent-[var(--text-primary)]"
              />
              {c.label}
            </label>
          ))}
        </div>
      </div>

      {person.can_manage && !person.is_demo && (
        <div className="mt-4 grid gap-3 border-t border-line pt-4 sm:grid-cols-2">
          <Field label="Sync history from" hint="Defaults to one year back. Older data fills in gradually.">
            <input
              type="date"
              className={inputClass}
              value={person.history_start ?? ''}
              max={toIsoDay(new Date())}
              onChange={(e) => update.mutate({ history_start: e.target.value || null })}
            />
          </Field>
          <Field label="Display name">
            <input
              className={inputClass}
              defaultValue={person.name}
              onBlur={(e) => e.target.value.trim() && e.target.value !== person.name && update.mutate({ name: e.target.value.trim() })}
            />
          </Field>
        </div>
      )}

      {person.is_me && person.has_login && <ChangePassword />}
      {me.is_admin && !person.is_me && <AdminActions person={person} onDelete={() => remove.mutate(undefined)} />}
      <ErrorNote error={update.error ?? sync.error ?? remove.error} />
    </Card>
  )
}

function KeyForm({ person }: { person: Person }) {
  const [open, setOpen] = useState(!person.key)
  const [key, setKey] = useState('')
  const [expiry, setExpiry] = useState('')
  const save = usePeopleMutation(async () => {
    const expires_on = expiry ? addDays(toIsoDay(new Date()), Number(expiry)) : null
    await api.put(`/api/people/${person.id}/garmin-key`, { api_key: key.trim(), expires_on })
  })
  const removeKey = usePeopleMutation(() => api.del(`/api/people/${person.id}/garmin-key`))

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    await save.mutateAsync(undefined).then(
      () => {
        setKey('')
        setOpen(false)
      },
      () => undefined,
    )
  }

  if (!open) {
    return (
      <div className="mt-3 flex gap-2">
        <Button onClick={() => setOpen(true)}>Replace key</Button>
        <Button variant="danger" onClick={() => window.confirm('Disconnect this Garmin key? Synced data stays.') && removeKey.mutate(undefined)}>
          Disconnect
        </Button>
      </div>
    )
  }
  return (
    <form onSubmit={submit} className="mt-3 space-y-3">
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_10rem]">
        <Field label="Personal API key">
          <input
            type="password"
            autoComplete="off"
            spellCheck={false}
            className={inputClass}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="Paste the key from Garmin Connect"
            required
            minLength={8}
          />
        </Field>
        <Field label="Key lifetime">
          <select className={inputClass} value={expiry} onChange={(e) => setExpiry(e.target.value)}>
            {EXPIRY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <p className="text-xs text-ink-2">
        The key is checked with Garmin, encrypted, and used to start the first sync. Pick the lifetime you chose
        so the dashboard can warn you before it runs out.
      </p>
      <ErrorNote error={save.error} />
      <div className="flex gap-2">
        <Button type="submit" variant="primary" disabled={save.isPending || key.trim().length < 8}>
          {save.isPending ? 'Checking with Garmin…' : 'Connect'}
        </Button>
        {person.key && (
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  )
}

const DATASET_LABELS: Record<string, string> = {
  daily_summaries: 'Daily summaries',
  sleep: 'Sleep',
  hrv: 'HRV',
  weight: 'Weight',
  activities: 'Activities',
}

function SyncDetails({ person }: { person: Person }) {
  const { data } = useSyncState(person.id, true)
  if (!data) return null
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-ink-2">
          <tr>
            <th className="py-1 pr-3 font-medium">Data</th>
            <th className="py-1 pr-3 font-medium">Covered</th>
            <th className="py-1 font-medium">Status</th>
          </tr>
        </thead>
        <tbody className="tabular">
          {data.datasets.map((d) => (
            <tr key={d.dataset} className="border-t border-line">
              <td className="py-1 pr-3 text-ink">{DATASET_LABELS[d.dataset] ?? d.dataset}</td>
              <td className="py-1 pr-3 text-ink-2">
                {d.synced_from && d.synced_through ? `${formatLongDay(d.synced_from)} – ${formatLongDay(d.synced_through)}` : '–'}
              </td>
              <td className="py-1 text-ink-2">{d.last_error ?? d.last_status ?? '–'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ChangePassword() {
  const [open, setOpen] = useState(false)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [done, setDone] = useState(false)
  const change = usePeopleMutation(() => api.post('/api/auth/password', { current_password: current, new_password: next }))
  if (!open) {
    return (
      <div className="mt-4 border-t border-line pt-4">
        <Button variant="ghost" onClick={() => setOpen(true)}>
          Change password
        </Button>
        {done && <span className="ml-2 text-xs text-good">Password changed</span>}
      </div>
    )
  }
  return (
    <form
      className="mt-4 grid gap-3 border-t border-line pt-4 sm:grid-cols-2"
      onSubmit={async (e) => {
        e.preventDefault()
        await change.mutateAsync(undefined).then(
          () => {
            setOpen(false)
            setDone(true)
          },
          () => undefined,
        )
      }}
    >
      <Field label="Current password">
        <input type="password" autoComplete="current-password" className={inputClass} value={current} onChange={(e) => setCurrent(e.target.value)} required />
      </Field>
      <Field label="New password">
        <input type="password" autoComplete="new-password" minLength={8} className={inputClass} value={next} onChange={(e) => setNext(e.target.value)} required />
      </Field>
      <ErrorNote error={change.error} />
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" variant="primary" disabled={change.isPending}>
          Save password
        </Button>
        <Button variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

function AdminActions({ person, onDelete }: { person: Person; onDelete: () => void }) {
  const [password, setPassword] = useState('')
  const reset = usePeopleMutation(() => api.post(`/api/people/${person.id}/password`, { password }))
  return (
    <div className="mt-4 flex flex-wrap items-end gap-2 border-t border-line pt-4">
      {person.has_login && (
        <>
          <Field label={`New password for ${person.name}`}>
            <input type="password" autoComplete="new-password" minLength={8} className={inputClass} value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Button onClick={() => reset.mutate(undefined, { onSuccess: () => setPassword('') })} disabled={password.length < 8 || reset.isPending}>
            Reset password
          </Button>
        </>
      )}
      <Button
        variant="danger"
        className="ml-auto"
        onClick={() => window.confirm(`Delete ${person.name} and all of their synced data? This can't be undone.`) && onDelete()}
      >
        Delete person
      </Button>
      <ErrorNote error={reset.error} />
      {reset.isSuccess && <span className="text-xs text-good">Password reset</span>}
    </div>
  )
}

function AddPerson() {
  const [name, setName] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [withLogin, setWithLogin] = useState(true)
  const create = usePeopleMutation(() =>
    api.post('/api/people', withLogin ? { name, username, password } : { name }),
  )
  return (
    <Card className="mt-6">
      <h2 className="text-base font-semibold text-ink">Add someone</h2>
      <p className="mt-1 text-sm text-ink-2">
        Give them a login so they can sign in from their own phone or laptop, add their own Garmin key and choose
        what to share. Without a login, you manage their key and settings for them.
      </p>
      <form
        className="mt-4 grid gap-3 sm:grid-cols-3"
        onSubmit={async (e) => {
          e.preventDefault()
          await create.mutateAsync(undefined).then(
            () => {
              setName('')
              setUsername('')
              setPassword('')
            },
            () => undefined,
          )
        }}
      >
        <Field label="Name">
          <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        {withLogin && (
          <>
            <Field label="Username">
              <input className={inputClass} value={username} autoCapitalize="none" onChange={(e) => setUsername(e.target.value)} required minLength={2} />
            </Field>
            <Field label="Temporary password" hint="They can change it after signing in.">
              <input type="password" autoComplete="new-password" className={inputClass} value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
            </Field>
          </>
        )}
        <label className="flex items-center gap-2 text-sm text-ink sm:col-span-3">
          <input type="checkbox" checked={withLogin} onChange={(e) => setWithLogin(e.target.checked)} className="h-4 w-4 accent-[var(--text-primary)]" />
          They'll sign in themselves
        </label>
        <ErrorNote error={create.error} />
        <div className="sm:col-span-3">
          <Button type="submit" variant="primary" disabled={create.isPending}>
            Add person
          </Button>
        </div>
      </form>
    </Card>
  )
}
