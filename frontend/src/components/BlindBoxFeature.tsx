import { lazy, Suspense } from 'react'

const BlindBox = lazy(() => import('../pages/BlindBoxPage'))

export function BlindBoxFeature({ onSaved }: { onSaved?: () => void }) {
  return <Suspense><BlindBox onSaved={onSaved} /></Suspense>
}
