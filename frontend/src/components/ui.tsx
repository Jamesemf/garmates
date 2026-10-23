import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { usePalette } from '../lib/theme'
import type { Person } from '../lib/types'

export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(' ')
}

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'

export function Button({
  variant = 'secondary',
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  const styles: Record<ButtonVariant, string> = {
    primary: 'bg-btn text-btn-text hover:opacity-90',
    secondary: 'bg-raised text-ink border border-line hover:bg-wash',
    ghost: 'text-ink-2 hover:bg-wash hover:text-ink',
    danger: 'text-bad border border-line hover:bg-wash',
  }
  return (
    <button
      type="button"
      {...props}
      className={cx(
        'inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50',
        styles[variant],
        className,
      )}
    />
  )
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <section className={cx('rounded-xl border border-line bg-surface p-4 sm:p-5', className)}>
      {children}
    </section>
  )
}

/** Colour key for a person: the mark carries the colour, the name stays in text ink. */
export function PersonKey({
  person,
  shape = 'dot',
  className,
}: {
  person: Pick<Person, 'name' | 'color_slot'>
  shape?: 'dot' | 'line' | 'rect'
  className?: string
}) {
  const palette = usePalette()
  const color = palette.series(person.color_slot)
  return (
    <span className={cx('inline-flex min-w-0 items-center gap-1.5', className)}>
      {shape === 'line' ? (
        <span className="inline-block h-0.5 w-3 shrink-0 rounded" style={{ background: color }} />
      ) : (
        <span
          className={cx('inline-block shrink-0', shape === 'dot' ? 'h-2.5 w-2.5 rounded-full' : 'h-2.5 w-2.5 rounded-sm')}
          style={{ background: color }}
        />
      )}
      <span className="truncate">{person.name}</span>
    </span>
  )
}

type Status = 'good' | 'warning' | 'critical' | 'neutral' | 'running'

/** Status always pairs colour with an icon and a label, never colour alone. */
export function StatusBadge({ status, children }: { status: Status; children: ReactNode }) {
  const icon = { good: '✓', warning: '!', critical: '✕', neutral: '•', running: '↻' }[status]
  const color = {
    good: 'text-good',
    warning: 'text-warn',
    critical: 'text-bad',
    neutral: 'text-ink-2',
    running: 'text-ink-2',
  }[status]
  return (
    <span className={cx('inline-flex items-center gap-1 text-xs font-medium', color)}>
      <span aria-hidden className={cx('inline-flex h-4 w-4 items-center justify-center rounded-full border border-current text-[10px] leading-none', status === 'running' && 'animate-spin')}>
        {icon}
      </span>
      {children}
    </span>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-10 text-center">
      <p className="text-sm font-medium text-ink">{title}</p>
      {children && <div className="max-w-md text-sm text-ink-2">{children}</div>}
    </div>
  )
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-ink-2">{subtitle}</p>}
      </div>
      {actions}
    </div>
  )
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T
  options: { value: T; label: string }[]
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg border border-line bg-raised p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={cx(
            'rounded-md px-2.5 py-1 text-xs font-medium transition',
            value === option.value ? 'bg-btn text-btn-text' : 'text-ink-2 hover:bg-wash hover:text-ink',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null
  const message = error instanceof Error ? error.message : String(error)
  return (
    <p role="alert" className="text-sm text-bad">
      {message}
    </p>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-ink">{label}</span>
      {children}
      {hint && <span className="text-xs text-ink-2">{hint}</span>}
    </label>
  )
}

export const inputClass =
  'w-full rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink placeholder:text-muted focus:outline-none focus-visible:outline-2'
