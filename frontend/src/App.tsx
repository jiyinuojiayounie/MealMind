import { Navigate, Route, Routes } from 'react-router'
import { FeaturePreview } from './components/FeaturePreview'
import { AppLayout } from './layouts/AppLayout'
import { TodayPage } from './pages/TodayPage'
import { WelcomePage } from './pages/WelcomePage'
import { featurePaths } from './types/navigation'

const previewFeatures = ['plan', 'log', 'pantry', 'profile'] as const

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<WelcomePage />} />
        <Route path={featurePaths.today} element={<TodayPage />} />
        {previewFeatures.map((feature) => (
          <Route
            key={feature}
            path={featurePaths[feature]}
            element={<FeaturePreview feature={feature} />}
          />
        ))}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
