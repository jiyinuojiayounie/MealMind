import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { PublicTodayReplan } from '../components/PublicTodayReplan'
import { PublicDailyPlan } from '../components/PublicDailyPlan'
import { BlindBoxFeature } from '../components/BlindBoxFeature'
import { TodayConsumedMeals } from '../components/TodayConsumedMeals'
import { TodayNutrition } from '../components/TodayNutrition'
import { TodayReplan } from '../components/TodayReplan'
import { canUseFoodLogs } from '../services/foodLogs'
import { featurePaths } from '../types/navigation'

const meals = ['breakfast', 'lunch', 'dinner'] as const

export function TodayPage() {
  const { t, i18n } = useTranslation()
  const [planRefresh, setPlanRefresh] = useState(0)
  const refreshPlans = () => setPlanRefresh((refresh) => refresh + 1)
  const today = new Date()
  const dateLabel = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
    dateStyle: 'full',
  }).format(today)

  return (
    <div className="grid gap-8">
      <div className="grid gap-3">
        <p className="date-label">{dateLabel}</p>
        <BlindBoxFeature onSaved={refreshPlans} />
      </div>
      {import.meta.env.PROD ? <PublicDailyPlan refresh={planRefresh} />
        : canUseFoodLogs() ? <TodayReplan key={planRefresh} /> : (
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
      {import.meta.env.PROD && <TodayConsumedMeals />}
      <TodayNutrition />
      {import.meta.env.PROD ? (
        <PublicTodayReplan refresh={planRefresh} onSaved={refreshPlans} />
      ) : <section className="assistant card" aria-labelledby="assistant-title">
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
      </section>}
    </div>
  )
}
