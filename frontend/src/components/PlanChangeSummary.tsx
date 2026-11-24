import { useTranslation } from 'react-i18next'
import type { PlannedMeal } from '../services/mealPlans'

export function PlanChangeSummary({ current, proposed }: { current: PlannedMeal[]; proposed: PlannedMeal[] }) {
  const { t } = useTranslation()
  return (
    <ul className="grid gap-2">
      {proposed.map((meal) => {
        const previous = current.find((entry) => entry.meal_type === meal.meal_type)
        return (
          <li key={meal.meal_type} className="wrap-anywhere rounded-xl bg-paper p-3 text-sm">
            <strong>{t(`pages.plan.meals.${meal.meal_type}`)} · {t(previous ? 'release.replaceSlot' : 'release.add')}</strong>
            {previous && <p>{t('release.currentMeal', { meal: previous.dishes.map((dish) => dish.name).join(' / ') })}</p>}
            <p>{t('release.proposedMeal', { meal: meal.dishes.map((dish) => dish.name).join(' / ') })}</p>
          </li>
        )
      })}
    </ul>
  )
}
