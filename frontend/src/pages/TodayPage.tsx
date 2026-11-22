import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { TodayNutrition } from '../components/TodayNutrition'
import { TodayReplan } from '../components/TodayReplan'
import { canUseFoodLogs } from '../services/foodLogs'
import { featurePaths } from '../types/navigation'

const shortcuts = ['plan', 'log', 'pantry', 'profile'] as const
const meals = ['breakfast', 'lunch', 'dinner'] as const

export function TodayPage() {
  const { t, i18n } = useTranslation()
  const today = new Date()
  const dateLabel = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
    dateStyle: 'full',
  }).format(today)

  return (
    <div className="grid gap-8">
      <div>
        <p className="date-label">{dateLabel}</p>
        <h1>{t('today.title')}</h1>
      </div>
      <section className="assistant card" aria-labelledby="assistant-title">
        <h2 id="assistant-title">{t('today.assistant')}</h2>
        <p id="assistant-status">{t('today.assistantHint')}</p>
        <input
          className="assistant-input"
          type="text"
          aria-labelledby="assistant-title"
          aria-describedby="assistant-status"
          placeholder={t('today.assistantExample')}
          disabled
        />
        <Link className="text-link" to={featurePaths.plan}>{t('today.direct')} <span aria-hidden="true">→</span></Link>
      </section>
      <section aria-labelledby="shortcuts-title">
        <h2 id="shortcuts-title">{t('today.shortcuts')}</h2>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {shortcuts.map((feature) => (
            <Link className="card shortcut" to={featurePaths[feature]} key={feature}>
              {t(`feature.${feature}`)} <span className="arrow" aria-hidden="true">↗</span>
            </Link>
          ))}
        </div>
      </section>
      <TodayNutrition />
      {import.meta.env.DEV && canUseFoodLogs() ? <TodayReplan /> : (
      <section aria-labelledby="overview-title">
        <h2 id="overview-title">{t('today.overview')}</h2>
        <ul className="card meal-list mt-3">
          {meals.map((meal) => (
            <li key={meal}>
              <strong>{t(`today.${meal}`)}</strong>
              <span>{t('today.empty')}</span>
            </li>
          ))}
        </ul>
      </section>
      )}
    </div>
  )
}
