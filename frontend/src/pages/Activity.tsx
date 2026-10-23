import { FilterBar } from '../components/FilterBar'
import { MetricChart } from '../components/MetricChart'
import { PageHeader } from '../components/ui'
import { useCatalog, useFilters, useSeries } from '../lib/hooks'

const METRICS = ['steps', 'intensity_minutes', 'active_kcal', 'distance_km', 'floors', 'total_kcal']

export function ActivityPage() {
  const filters = useFilters()
  const { byKey } = useCatalog()
  const series = useSeries(filters.people, METRICS, filters.start, filters.end, filters.bucket)
  const common = { people: filters.people, response: series.data, bucket: filters.bucket, loading: series.isFetching }

  return (
    <>
      <PageHeader title="Daily activity" subtitle="Everyday movement outside of (and including) workouts." />
      <FilterBar filters={filters} />
      <div className="grid gap-4 lg:grid-cols-2">
        <MetricChart metric={byKey.steps} kind="bar" {...common} />
        <MetricChart
          metric={byKey.intensity_minutes}
          kind="bar"
          {...common}
          referenceY={filters.bucket === 'week' ? 150 : undefined}
          subtitle={filters.bucket === 'week' ? 'Weekly total · line marks the 150-minute guideline' : undefined}
        />
        <MetricChart metric={byKey.active_kcal} {...common} />
        <MetricChart metric={byKey.distance_km} {...common} />
        <MetricChart metric={byKey.floors} kind="bar" {...common} />
        <MetricChart metric={byKey.total_kcal} {...common} />
      </div>
    </>
  )
}
