import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'
import { useSearchParams } from 'react-router'
import { api } from './api'
import { addDays, toIsoDay } from './format'
import type {
  ActivityDetail,
  Activity,
  Bucket,
  Catalog,
  DayResponse,
  MetricDef,
  Person,
  SeriesResponse,
  SummaryResponse,
  SyncStateResponse,
  WorkoutStats,
} from './types'

// --- auth & people -------------------------------------------------------------------------

export function useAuthState() {
  return useQuery({
    queryKey: ['auth'],
    queryFn: () => api.get<{ setup_required: boolean; me: Person | null }>('/api/auth/state'),
    staleTime: 60_000,
  })
}

export function usePeople() {
  return useQuery({
    queryKey: ['people'],
    queryFn: () => api.get<Person[]>('/api/people'),
    // Poll while any sync is running so progress shows up without a reload.
    refetchInterval: (query) => (query.state.data?.some((p) => p.syncing) ? 4000 : 60_000),
  })
}

export function useCatalog() {
  const query = useQuery({
    queryKey: ['catalog'],
    queryFn: () => api.get<Catalog>('/api/catalog'),
    staleTime: Infinity,
  })
  const byKey = useMemo(() => {
    const map: Record<string, MetricDef> = {}
    for (const m of query.data?.metrics ?? []) map[m.key] = m
    return map
  }, [query.data])
  return { ...query, byKey }
}

/** Invalidate everything that depends on synced data (after a sync or people change). */
export function useRefreshAll() {
  const client = useQueryClient()
  return () => client.invalidateQueries()
}

export function usePeopleMutation<TBody = unknown, TResult = unknown>(
  fn: (body: TBody) => Promise<TResult>,
) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ['people'] })
      client.invalidateQueries({ queryKey: ['auth'] })
    },
  })
}

// --- global filters (kept in the URL) ------------------------------------------------------

export const RANGE_PRESETS = [
  { key: '7d', label: 'Last 7 days', days: 7 },
  { key: '30d', label: 'Last 30 days', days: 30 },
  { key: '90d', label: 'Last 90 days', days: 90 },
  { key: '6m', label: 'Last 6 months', days: 182 },
  { key: '1y', label: 'Last 12 months', days: 365 },
] as const

export interface Filters {
  range: string
  start: string
  end: string
  days: number
  bucket: Bucket
  bucketChoice: Bucket | 'auto'
  people: Person[]
  peopleIds: number[]
  allPeople: Person[]
  set: (changes: Record<string, string | null>) => void
}

export function autoBucket(days: number): Bucket {
  if (days <= 62) return 'day'
  if (days <= 240) return 'week'
  return 'month'
}

export function useFilters(defaultRange = '30d'): Filters {
  const [params, setParams] = useSearchParams()
  const { data: allPeople = [] } = usePeople()

  const today = toIsoDay(new Date())
  const range = params.get('range') ?? defaultRange
  let start: string
  let end: string
  if (range === 'custom' && params.get('start') && params.get('end')) {
    start = params.get('start')!
    end = params.get('end')!
  } else {
    const preset = RANGE_PRESETS.find((p) => p.key === range) ?? RANGE_PRESETS[1]
    end = today
    start = addDays(today, -(preset.days - 1))
  }
  const days = Math.round((Date.parse(end) - Date.parse(start)) / 86_400_000) + 1
  const bucketParam = params.get('bucket')
  const bucketChoice = (bucketParam === 'day' || bucketParam === 'week' || bucketParam === 'month'
    ? bucketParam
    : 'auto') as Bucket | 'auto'
  const bucket = bucketChoice === 'auto' ? autoBucket(days) : bucketChoice

  const visiblePeople = allPeople.filter((p) => p.visible_categories.length > 0)
  // By default show everyone who has (or is getting) data; key-less profiles can be toggled on.
  const hasData = (p: Person) => p.is_demo || p.key !== null || p.last_sync !== null
  const defaults = visiblePeople.some(hasData) ? visiblePeople.filter(hasData) : visiblePeople
  const requested = params.get('people')
  const peopleIds = requested
    ? requested.split(',').map(Number).filter((id) => visiblePeople.some((p) => p.id === id))
    : defaults.map((p) => p.id)
  const people = visiblePeople.filter((p) => peopleIds.includes(p.id))

  return {
    range,
    start,
    end,
    days,
    bucket,
    bucketChoice,
    people,
    peopleIds,
    allPeople: visiblePeople,
    set: (changes) => {
      const next = new URLSearchParams(params)
      for (const [key, value] of Object.entries(changes)) {
        if (value === null) next.delete(key)
        else next.set(key, value)
      }
      setParams(next, { replace: true })
    },
  }
}

// --- data ----------------------------------------------------------------------------------

const ids = (people: Person[] | number[]) =>
  people.map((p) => (typeof p === 'number' ? p : p.id)).join(',')

export function useSeries(
  people: Person[],
  metrics: string[],
  start: string,
  end: string,
  bucket: Bucket,
) {
  return useQuery({
    queryKey: ['series', ids(people), metrics.join(','), start, end, bucket],
    queryFn: () =>
      api.get<SeriesResponse>('/api/series', {
        people: ids(people),
        metrics: metrics.join(','),
        start,
        end,
        bucket,
      }),
    enabled: people.length > 0 && metrics.length > 0,
    placeholderData: keepPreviousData,
  })
}

export function useSummary(
  people: Person[],
  metrics: string[],
  start: string,
  end: string,
  baselineDays = 30,
) {
  return useQuery({
    queryKey: ['summary', ids(people), metrics.join(','), start, end, baselineDays],
    queryFn: () =>
      api.get<SummaryResponse>('/api/summary', {
        people: ids(people),
        metrics: metrics.join(','),
        start,
        end,
        baseline_days: baselineDays,
      }),
    enabled: people.length > 0,
    placeholderData: keepPreviousData,
  })
}

export function useActivities(people: Person[], start: string, end: string, sport?: string) {
  return useQuery({
    queryKey: ['activities', ids(people), start, end, sport ?? ''],
    queryFn: () =>
      api.get<{ activities: Activity[] }>('/api/activities', {
        people: ids(people),
        start,
        end,
        sport,
        limit: 500,
      }),
    enabled: people.length > 0,
    placeholderData: keepPreviousData,
  })
}

export function useActivity(activityId: number) {
  return useQuery({
    queryKey: ['activity', activityId],
    queryFn: () => api.get<ActivityDetail>(`/api/activities/${activityId}`),
    staleTime: Infinity,
  })
}

export function useWorkoutStats(people: Person[], start: string, end: string, bucket: Bucket) {
  return useQuery({
    queryKey: ['workout-stats', ids(people), start, end, bucket],
    queryFn: () =>
      api.get<{ people: Record<string, WorkoutStats> }>('/api/workouts/stats', {
        people: ids(people),
        start,
        end,
        bucket,
      }),
    enabled: people.length > 0,
    placeholderData: keepPreviousData,
  })
}

export function useDay(people: Person[], date: string) {
  return useQuery({
    queryKey: ['day', ids(people), date],
    queryFn: () => api.get<DayResponse>('/api/day', { people: ids(people), date }),
    enabled: people.length > 0,
    placeholderData: keepPreviousData,
  })
}

export function useSyncState(personId: number, enabled: boolean) {
  return useQuery({
    queryKey: ['sync-state', personId],
    queryFn: () => api.get<SyncStateResponse>(`/api/people/${personId}/sync-state`),
    enabled,
    refetchInterval: (query) => (query.state.data?.syncing ? 4000 : false),
  })
}
