import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getSavedMealPlan } from '../services/mealPlanRepository'
import type { SavedMealPlan } from '../services/mealPlanRepository'
import { localDateTimeValue } from '../types/localTime'
import { MealPlanResult } from './MealPlanResult'

const slots = ['breakfast', 'lunch', 'dinner', 'snack'] as const

export function PublicDailyPlan({ refresh }: { refresh: number }) {
  const { t } = useTranslation()
  const day = localDateTimeValue(new Date()).slice(0, 10)
  const [loaded, setLoaded] = useState<{ day: string; refresh: number; record?: SavedMealPlan | null }>()
  const current = loaded?.day === day && loaded.refresh === refresh ? loaded : undefined

  useEffect(() => {
    let active = true
    void getSavedMealPlan(day).then(
      (record) => { if (active) setLoaded({ day, refresh, record }) },
      () => { if (active) setLoaded({ day, refresh }) },
    )
    return () => { active = false }
  }, [day, refresh])

  const plan = current?.record?.revisions.at(-1)
  return (
    <section className="card grid min-w-0 gap-3 p-4 sm:p-6" aria-labelledby="public-plan-title">
      <h2 id="public-plan-title">{t('today.overview')}</h2>
      <p className="text-sm text-muted">{t('release.browserOnly')}</p>
      {!current ? <p role="status">{t('pages.plan.saved.loading')}</p> : current.record === undefined ? (
        <p role="alert">{t('pages.plan.saved.errors.unavailable')}</p>
      ) : (
        <>
          {plan && <p className="text-sm text-muted">{t('replan.active', { revision: plan.revision })}</p>}
          <ul className="meal-list">
            {slots.filter((slot) => slot !== 'snack' || plan?.plan.meals.some((meal) => meal.meal_type === slot)).map((slot) => (
              <li key={slot}>
                <strong>{t(`pages.plan.meals.${slot}`)}</strong>
                <span className="min-w-0 wrap-anywhere">{plan?.plan.meals.find((meal) => meal.meal_type === slot)
                  ?.dishes.map((dish) => dish.name).join(' / ') ?? t('today.empty')}</span>
              </li>
            ))}
          </ul>
          {plan && <details><summary className="min-h-11 cursor-pointer py-2">{t('release.planDetails')}</summary>
            <MealPlanResult plan={plan.plan} language={plan.language} />
          </details>}
          {current.record && current.record.revisions.length > 1 && (
            <details>
              <summary className="min-h-11 cursor-pointer py-2">{t('release.history')}</summary>
              {current.record.revisions.slice(0, -1).reverse().map((version) => (
                <details key={version.revision} className="mb-2 rounded-xl border border-border p-3">
                  <summary className="min-h-11 cursor-pointer py-2">{t('release.version', { revision: version.revision })}</summary>
                  <MealPlanResult plan={version.plan} language={version.language} />
                </details>
              ))}
            </details>
          )}
        </>
      )}
    </section>
  )
}
