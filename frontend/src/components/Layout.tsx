import { useQueryClient } from '@tanstack/react-query'
import { Link, NavLink, Outlet, useLocation } from 'react-router'
import { api } from '../lib/api'
import { usePeople } from '../lib/hooks'
import { useTheme, type ThemeChoice } from '../lib/theme'
import type { Person } from '../lib/types'
import { cx, StatusBadge } from './ui'

const NAV = [
  { to: '/', label: 'Overview' },
  { to: '/sleep', label: 'Sleep & recovery' },
  { to: '/activity', label: 'Daily activity' },
  { to: '/workouts', label: 'Workouts' },
  { to: '/body', label: 'Body & health' },
  { to: '/compare', label: 'Compare' },
  { to: '/day', label: 'Day view' },
  { to: '/people', label: 'People & keys' },
]

function ThemePicker() {
  const { choice, setChoice } = useTheme()
  return (
    <label className="flex items-center gap-2 text-xs text-ink-2">
      Theme
      <select
        value={choice}
        onChange={(e) => setChoice(e.target.value as ThemeChoice)}
        className="rounded-md border border-line bg-raised px-1.5 py-1 text-xs text-ink"
      >
        <option value="system">System</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </label>
  )
}

function KeyBanner({ people }: { people: Person[] }) {
  const problems = people.filter(
    (p) => p.can_manage && p.key && (p.key.status === 'invalid' || p.key.expiring_soon),
  )
  const syncing = people.filter((p) => p.syncing)
  if (!problems.length && !syncing.length) return null
  return (
    <div className="mb-4 space-y-2">
      {problems.map((p) => (
        <div key={p.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-sm">
          <StatusBadge status={p.key!.status === 'invalid' ? 'critical' : 'warning'}>
            {p.key!.status === 'invalid' ? 'Key not working' : 'Key expiring'}
          </StatusBadge>
          <span className="text-ink-2">
            {p.key!.status === 'invalid'
              ? `Garmin rejected ${p.is_me ? 'your' : `${p.name}'s`} Personal API key, so syncing has stopped.`
              : `${p.is_me ? 'Your' : `${p.name}'s`} Garmin key expires in ${p.key!.days_left} day${p.key!.days_left === 1 ? '' : 's'}.`}
          </span>
          <Link to="/people" className="font-medium text-ink underline underline-offset-2">
            Replace key
          </Link>
        </div>
      ))}
      {syncing.length > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink-2">
          <StatusBadge status="running">Syncing</StatusBadge>
          Pulling Garmin data for {syncing.map((p) => p.name).join(' and ')}. Recent days arrive
          first; older history fills in over the next few minutes.
        </div>
      )}
    </div>
  )
}

export function Layout({ me }: { me: Person }) {
  const location = useLocation()
  const client = useQueryClient()
  const { data: people = [] } = usePeople()

  const signOut = async () => {
    await api.post('/api/auth/logout')
    client.clear()
    window.location.assign('/')
  }

  const navLink = (item: (typeof NAV)[number], compact = false) => (
    <NavLink
      key={item.to}
      to={{ pathname: item.to, search: item.to === '/people' ? '' : location.search }}
      end={item.to === '/'}
      className={({ isActive }) =>
        cx(
          'rounded-lg px-3 py-2 text-sm whitespace-nowrap transition',
          compact ? 'shrink-0' : 'block',
          isActive ? 'bg-raised font-medium text-ink shadow-sm ring-1 ring-line' : 'text-ink-2 hover:bg-wash hover:text-ink',
        )
      }
    >
      {item.label}
    </NavLink>
  )

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[220px_1fr]">
      <aside className="hidden border-r border-line lg:flex lg:flex-col lg:gap-6 lg:px-3 lg:py-5">
        <Link to="/" className="px-3 text-base font-semibold tracking-tight text-ink">
          Household Health
        </Link>
        <nav aria-label="Main" className="flex flex-col gap-0.5">
          {NAV.map((item) => navLink(item))}
        </nav>
        <div className="mt-auto space-y-3 px-3 text-xs text-ink-2">
          <ThemePicker />
          <div className="flex items-center justify-between gap-2">
            <span className="truncate">Signed in as {me.name}</span>
            <button type="button" onClick={signOut} className="font-medium text-ink hover:underline">
              Sign out
            </button>
          </div>
        </div>
      </aside>

      <div className="min-w-0">
        <header className="sticky top-0 z-[1000] border-b border-line bg-page/95 backdrop-blur lg:hidden">
          <div className="flex items-center justify-between px-4 pt-3">
            <Link to="/" className="text-base font-semibold tracking-tight text-ink">
              Household Health
            </Link>
            <div className="flex items-center gap-3">
              <ThemePicker />
              <button type="button" onClick={signOut} className="text-xs font-medium text-ink">
                Sign out
              </button>
            </div>
          </div>
          <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-3 py-2">
            {NAV.map((item) => navLink(item, true))}
          </nav>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
          <KeyBanner people={people} />
          <Outlet />
        </main>
      </div>
    </div>
  )
}
