import { Navigate, Route, Routes } from 'react-router'
import { Layout } from './components/Layout'
import { EmptyState } from './components/ui'
import { useAuthState } from './lib/hooks'
import { ActivityDetailPage } from './pages/ActivityDetail'
import { ActivityPage } from './pages/Activity'
import { AuthPage } from './pages/Auth'
import { BodyPage } from './pages/Body'
import { ComparePage } from './pages/Compare'
import { DayPage } from './pages/Day'
import { OverviewPage } from './pages/Overview'
import { PeoplePage } from './pages/People'
import { SleepPage } from './pages/Sleep'
import { WorkoutsPage } from './pages/Workouts'

export default function App() {
  const { data, isLoading, error } = useAuthState()

  if (isLoading) return null
  if (error || !data) {
    return <EmptyState title="Can't reach the dashboard server">Is the backend running on port 8000?</EmptyState>
  }
  if (data.setup_required || !data.me) return <AuthPage setup={data.setup_required} />

  return (
    <Routes>
      <Route element={<Layout me={data.me} />}>
        <Route index element={<OverviewPage />} />
        <Route path="sleep" element={<SleepPage />} />
        <Route path="activity" element={<ActivityPage />} />
        <Route path="workouts" element={<WorkoutsPage />} />
        <Route path="workouts/:activityId" element={<ActivityDetailPage />} />
        <Route path="body" element={<BodyPage />} />
        <Route path="compare" element={<ComparePage />} />
        <Route path="day" element={<DayPage />} />
        <Route path="people" element={<PeoplePage me={data.me} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
