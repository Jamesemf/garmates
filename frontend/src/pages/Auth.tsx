import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { Button, ErrorNote, Field, inputClass } from '../components/ui'
import { api } from '../lib/api'

export function AuthPage({ setup }: { setup: boolean }) {
  const client = useQueryClient()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (setup) {
        await api.post('/api/auth/setup', { name, username, password })
        navigate('/people', { replace: true })
      } else {
        await api.post('/api/auth/login', { username, password })
      }
      await client.invalidateQueries()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl border border-line bg-surface p-6">
        <div>
          <h1 className="text-lg font-semibold text-ink">Garmates</h1>
          <p className="mt-1 text-sm text-ink-2">
            {setup
              ? 'Create the first account. You become the admin and can add other people afterwards.'
              : 'Sign in to see your Garmin dashboard.'}
          </p>
        </div>
        {setup && (
          <Field label="Your name">
            <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
          </Field>
        )}
        <Field label="Username">
          <input
            className={inputClass}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoCapitalize="none"
            required
            autoFocus={!setup}
          />
        </Field>
        <Field label="Password" hint={setup ? 'At least 8 characters.' : undefined}>
          <input
            className={inputClass}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={setup ? 'new-password' : 'current-password'}
            minLength={setup ? 8 : undefined}
            required
          />
        </Field>
        <ErrorNote error={error} />
        <Button type="submit" variant="primary" className="w-full" disabled={busy}>
          {setup ? 'Create account' : 'Sign in'}
        </Button>
      </form>
    </div>
  )
}
