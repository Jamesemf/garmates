import { FilterBar } from '../components/FilterBar'
import { MetricChart } from '../components/MetricChart'
import { PageHeader } from '../components/ui'
import { useCatalog, useFilters, useSeries } from '../lib/hooks'

const METRICS = ['weight', 'body_fat', 'bmi', 'spo2', 'respiration', 'hydration', 'fitness_age']

export function BodyPage() {
  const filters = useFilters('90d')
  const { byKey } = useCatalog()
  const series = useSeries(filters.people, METRICS, filters.start, filters.end, filters.bucket)
  const common = { people: filters.people, response: series.data, bucket: filters.bucket, loading: series.isFetching }

  return (
    <>
      <PageHeader title="Body & health" subtitle="Body composition from scales, plus overnight vitals." />
      <FilterBar filters={filters} />
      <div className="grid gap-4 lg:grid-cols-2">
        <MetricChart metric={byKey.weight} {...common} connectNulls subtitle="Each person on their own scale - compare trends, not levels" />
        <MetricChart metric={byKey.body_fat} {...common} connectNulls />
        <MetricChart metric={byKey.spo2} {...common} />
        <MetricChart metric={byKey.respiration} {...common} />
        <MetricChart metric={byKey.hydration} kind="bar" {...common} />
        <MetricChart metric={byKey.fitness_age} {...common} connectNulls subtitle="Recorded once per sync" />
      </div>
    </>
  )
}
