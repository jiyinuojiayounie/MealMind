import { useTranslation } from 'react-i18next'
import type { MealPlan, MealPlanRequest } from '../services/mealPlans'

type Props = { plan: MealPlan; language: MealPlanRequest['language'] }

export function MealPlanResult({ plan, language }: Props) {
  const { t, i18n } = useTranslation()
  const number = new Intl.NumberFormat(i18n.resolvedLanguage, { maximumSignificantDigits: 12 })

  return (
    <section className="grid gap-4 wrap-anywhere" aria-labelledby="meal-plan-title">
      <div>
        <h2 id="meal-plan-title" className="text-2xl" lang={language}>{plan.title}</h2>
        <p className="mt-2 text-muted">
          <strong>{t('pages.plan.explanation')}</strong>{' '}
          <span lang={language}>{plan.explanation}</span>
        </p>
      </div>

      {plan.meals.map((meal) => (
        <article key={meal.meal_type} className="card p-5 sm:p-6">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="mt-0 text-xl">{t(`pages.plan.meals.${meal.meal_type}`)}</h3>
            <p className="rounded-full bg-sage px-3 py-1 text-sm font-medium text-forest">
              {t('pages.plan.estimatedTime', { minutes: meal.estimated_preparation_minutes })}
            </p>
          </div>
          {meal.dishes.map((dish, index) => (
            <div key={index} className="mt-4 border-t border-border pt-4">
              <h4 className="text-lg font-semibold" lang={language}>{dish.name}</h4>
              <div className="mt-3 grid gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
                <div>
                  <h5 className="font-semibold">{t('pages.plan.ingredients')}</h5>
                  <ul className="mt-1 list-disc space-y-1 ps-5">
                    {dish.ingredients.map((ingredient, ingredientIndex) => (
                      <li key={ingredientIndex}>
                        <span lang={language}>{ingredient.name}</span>{' '}
                        {number.format(ingredient.quantity)} <span lang={language}>{ingredient.unit}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h5 className="font-semibold">{t('pages.plan.instructions')}</h5>
                  <ol className="mt-1 list-decimal space-y-1 ps-5" lang={language}>
                    {dish.instructions.map((step, stepIndex) => <li key={stepIndex}>{step}</li>)}
                  </ol>
                </div>
              </div>
            </div>
          ))}
        </article>
      ))}

      {plan.additional_ingredients.length > 0 && (
        <aside className="card p-5 sm:p-6">
          <h3 className="mt-0">{t('pages.plan.additional')}</h3>
          <ul className="mt-2 list-disc space-y-1 ps-5" lang={language}>
            {plan.additional_ingredients.map((ingredient, index) => <li key={index}>{ingredient}</li>)}
          </ul>
        </aside>
      )}
    </section>
  )
}
