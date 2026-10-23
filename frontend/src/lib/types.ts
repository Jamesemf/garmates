export type Category = 'sleep' | 'activity' | 'workouts' | 'body'
export type Bucket = 'day' | 'week' | 'month'

export interface Preferences {
  distance: 'km' | 'mi'
  weight: 'kg' | 'lb' | 'st'
  volume: 'ml' | 'floz'
  elevation: 'm' | 'ft'
  week_start: 'monday' | 'sunday'
  time_format: '24h' | '12h'
}

export interface KeyInfo {
  hint: string | null
  status: 'ok' | 'invalid' | 'unverified'
  expires_on: string | null
  days_left: number | null
  expiring_soon: boolean
  last_error: string | null
  garmin_display_name: string | null
}

export interface SyncInfo {
  status: 'running' | 'ok' | 'partial' | 'error'
  started_at: string
  finished_at: string | null
  message: string | null
}

export interface Person {
  id: number
  name: string
  color_slot: number
  is_admin: boolean
  is_demo: boolean
  is_me: boolean
  can_manage: boolean
  has_login: boolean
  username: string | null
  shared_categories: Category[]
  visible_categories: Category[]
  history_start: string | null
  /** Effective display preferences (only for people you manage, including yourself). */
  preferences: Preferences | null
  preference_overrides: Partial<Preferences> | null
  key: KeyInfo | null
  syncing: boolean
  last_sync: SyncInfo | null
}

export interface MetricDef {
  key: string
  label: string
  unit: string
  category: Category
  direction: 'up' | 'down' | 'none'
  agg: 'mean' | 'sum'
  decimals: number
  description: string
  quantity: 'distance_km' | 'mass_kg' | 'volume_ml' | null
}

export interface Catalog {
  categories: { key: Category; label: string }[]
  metrics: MetricDef[]
}

export type Point = { date: string } & Record<string, number | null | string>

export interface SeriesResponse {
  start: string
  end: string
  bucket: Bucket
  people: Record<string, { points: Point[]; hidden: string[] }>
}

export interface MetricSummary {
  value: number | null
  latest: number | null
  latest_date: string | null
  baseline: number | null
  delta_pct: number | null
  z: number | null
  n: number
  baseline_n: number
}

export interface SummaryResponse {
  start: string
  end: string
  baseline_days: number
  people: Record<string, { metrics: Record<string, MetricSummary>; hidden: string[] }>
}

export interface Activity {
  activity_id: number
  person_id: number
  date: string
  name: string | null
  type_key: string | null
  sport: string
  start_local: string | null
  duration_s: number | null
  moving_s: number | null
  distance_m: number | null
  elevation_gain_m: number | null
  avg_speed_mps: number | null
  max_speed_mps: number | null
  avg_hr: number | null
  max_hr: number | null
  calories: number | null
  aerobic_te: number | null
  anaerobic_te: number | null
  training_load: number | null
  vo2max: number | null
  hr_zone_s: (number | null)[] | null
  avg_power: number | null
  avg_cadence: number | null
  has_polyline: boolean
  is_pr: boolean
}

export type TrackPoint = [number, number | null, number | null, number | null, number | null, number | null, number | null]

export interface ActivityDetail extends Activity {
  track: { points: TrackPoint[]; error: string | null }
}

export interface SportStats {
  count: number
  hours: number
  km: number
  load: number
}

export interface WorkoutStats {
  hidden?: boolean
  by_sport: Record<string, SportStats>
  buckets: { date: string; sports: Record<string, SportStats> }[]
  zone_minutes: number[]
  load: { date: string; acute: number; chronic: number; ratio: number | null }[]
}

export interface DayPerson {
  hidden: Category[]
  sleep?: {
    score: number | null
    duration_s: number | null
    deep_s: number | null
    light_s: number | null
    rem_s: number | null
    awake_s: number | null
    start_local: string | null
    end_local: string | null
    avg_hr: number | null
    feedback: string | null
  } | null
  hrv?: { last_night_avg: number | null; weekly_avg: number | null; status: string | null } | null
  daily?: {
    steps: number | null
    step_goal: number | null
    rhr: number | null
    stress_avg: number | null
    bb_max: number | null
    bb_min: number | null
  }
  heart_rate?: [number, number][]
  body_battery?: [number, number][]
  detail_error?: string | null
}

export interface DayResponse {
  date: string
  people: Record<string, DayPerson>
}

export interface SyncStateResponse {
  syncing: boolean
  datasets: {
    dataset: string
    synced_from: string | null
    synced_through: string | null
    last_status: string | null
    last_error: string | null
  }[]
  runs: SyncInfo[]
}

export type GoalStatus = 'met' | 'in_progress' | 'on_track' | 'behind' | 'missed' | 'no_data'
export type Period = 'day' | 'week' | 'month'

export interface Goal {
  id: number
  person_id: number
  metric_key: string
  comparison: 'at_least' | 'at_most'
  target: number
  period: Period
  current: {
    start: string
    end: string
    value: number | null
    elapsed_days: number
    total_days: number
    expected: number | null
    status: GoalStatus
  }
  history: { start: string; value: number | null; met: boolean | null }[]
  streak: number
  hit_rate: number | null
}

export type Scoring = 'total' | 'average' | 'improvement'

export interface ChallengeEntry {
  person_id: number
  hidden: boolean
  score: number | null
  days: number
  rank?: number
  baseline?: number | null
}

export interface Challenge {
  id: number
  name: string
  metric_key: string
  scoring: Scoring
  start: string
  end: string
  status: 'upcoming' | 'active' | 'finished'
  days_left: number
  created_by: number | null
  entries: ChallengeEntry[]
  race: ({ date: string } & Record<string, number | string>)[]
}
