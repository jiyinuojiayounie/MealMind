import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { featurePaths } from '../types/navigation'

export function ProfilePage() {
  const { t } = useTranslation()

  return (
    <div className="grid gap-6">
      <div>
        <h1>{t('feature.profile')}</h1>
        <p className="intro">{t('pages.profile.intro')}</p>
      </div>
      <section className="card preview" aria-labelledby="preview-title">
        <h2 id="preview-title">{t('preview')}</h2>
        <p>{t('pages.profile.status')}</p>
      </section>
      <Link className="text-link justify-self-start" to={featurePaths.today}>
        <span aria-hidden="true">←</span> {t('back')}
      </Link>
    </div>
  )
}
