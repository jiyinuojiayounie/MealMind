import { Navigate, Route, Routes } from 'react-router'
import { BlindBoxFeature } from './components/BlindBoxFeature'
import { AppLayout } from './layouts/AppLayout'
import { LogPage } from './pages/LogPage'
import { PlanningPage } from './pages/PlanningPage'
import { ProfilePage } from './pages/ProfilePage'
import { TodayPage } from './pages/TodayPage'
import { WelcomePage } from './pages/WelcomePage'
import { featurePaths } from './types/navigation'

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<WelcomePage />} />
        <Route path={featurePaths.today} element={<TodayPage />} />
        <Route path={featurePaths.blindBox} element={<BlindBoxFeature />} />
        <Route path={featurePaths.plan} element={<PlanningPage />} />
        <Route path={featurePaths.log} element={<LogPage />} />
        <Route path={featurePaths.profile} element={<ProfilePage />} />
        <Route path="/pantry" element={<Navigate to={featurePaths.today} replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
