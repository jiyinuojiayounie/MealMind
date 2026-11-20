import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { featurePaths } from '../types/navigation'

const choices = [
  { key: 'profile', path: featurePaths.profile },
  { key: 'direct', path: featurePaths.today },
] as const

export function WelcomePage() {
  const { t } = useTranslation()

  return (
    <div className="welcome">
      <h1>{t('welcome.title')}</h1>
      <p className="intro">{t('welcome.intro')}</p>
      <div className="welcome-choices grid gap-4 sm:grid-cols-2">
        {choices.map(({ key, path }) => (
          <Link className="choice card" to={path} key={key}>
            <strong>{t(`welcome.${key}`)}</strong>
            <span>{t(`welcome.${key}Detail`)}</span>
            <span className="arrow" aria-hidden="true">↗</span>
          </Link>
        ))}
      </div>
    </div>
  )
}
