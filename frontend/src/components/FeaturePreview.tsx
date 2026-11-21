import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { featurePaths } from '../types/navigation'
import type { Feature } from '../types/navigation'

type Props = { feature: Exclude<Feature, 'today' | 'plan'> }

export function FeaturePreview({ feature }: Props) {
  const { t } = useTranslation()

  return (
    <div className="grid gap-6">
      <div>
        <h1>{t(`feature.${feature}`)}</h1>
        <p className="intro">{t(`pages.${feature}.intro`)}</p>
      </div>
      <section className="card preview" aria-labelledby="preview-title">
        <h2 id="preview-title">{t('preview')}</h2>
        <p>{t(`pages.${feature}.status`)}</p>
      </section>
      <Link className="text-link justify-self-start" to={featurePaths.today}>
        <span aria-hidden="true">←</span> {t('back')}
      </Link>
    </div>
  )
}
