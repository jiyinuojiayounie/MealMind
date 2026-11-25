import { demoMealPlan, reviewedMealCandidates } from './blindBox'
import type { FoodLog } from './foodLogs'
import { mealTypes } from './mealPlans'
import type { MealPlanRequest, MealType } from './mealPlans'
import { createPlanId, settingsForMeal } from './mealPlanRepository'
import type { PlanAcceptance, SavedMealPlan } from './mealPlanRepository'

export const quickReplanMinutes = 20
const noodles = new Set(['ingredient_wheat_noodles', 'ingredient_rice_vermicelli', 'ingredient_packed_udon'])
const languages = ['zh-CN', 'en-US'] as const

function label(name: string) {
  return name.normalize('NFKC').toLowerCase().replace(/[\s\p{P}]/gu, '')
}

function ingredientLabel(name: string) {
  return name.normalize('NFKC').toLowerCase().trim().replace(/\s+/gu, ' ')
}

export function suggestLocalMeal(
  record: SavedMealPlan | null, logs: FoodLog[], target: MealType,
  options: { noodles: boolean; quick: boolean; avoidRepeat: boolean; hasRestriction: boolean },
  language: MealPlanRequest['language'], serving: string,
): PlanAcceptance | undefined {
  const active = record?.revisions.at(-1)
  if (record?.lockedMealTypes?.includes(target) || logs.some((log) => log.meal_type === target)) return
  const saved = active?.plan.meals.some((meal) => meal.meal_type === target) ? settingsForMeal(active, target) : undefined
  const constraints = saved?.constraints
  const maxMinutes = Math.min(constraints?.cooking_time_limit ?? 480, options.quick ? quickReplanMinutes : 480)
  const earlier = (slot: MealType) => mealTypes.indexOf(slot) < mealTypes.indexOf(target)
  const avoided = new Set([
    ...(active?.plan.meals ?? []).filter((meal) => meal.meal_type === target || (options.avoidRepeat && earlier(meal.meal_type)))
      .flatMap((meal) => meal.dishes.map((dish) => label(dish.name))),
    ...(options.avoidRepeat ? logs.filter((log) => log.meal_type === 'unspecified' || earlier(log.meal_type))
      .flatMap((log) => log.items.map((item) => label(item.name))) : []),
  ])
  const available = new Set((constraints?.available_ingredients ?? []).map(ingredientLabel))
  const candidates = reviewedMealCandidates(target, options.hasRestriction)
    .filter((recipe) => !options.noodles || recipe.ingredients.some((ingredient) => noodles.has(ingredient.ingredient_id)))
    .filter((recipe) => languages.every((lang) => !avoided.has(label(recipe.names[lang]))))
    .map((recipe) => ({ recipe, plan: demoMealPlan(recipe, target, language, serving) }))
    .filter(({ recipe, plan }) => plan.meals[0].estimated_preparation_minutes <= maxMinutes
      && (constraints?.ingredient_mode !== 'existing' || demoMealPlan(recipe, target, saved?.language ?? language, serving)
        .meals[0].dishes.every((dish) => dish.ingredients.every((ingredient) => available.has(ingredientLabel(ingredient.name))))))
    .sort((a, b) => a.plan.meals[0].estimated_preparation_minutes - b.plan.meals[0].estimated_preparation_minutes
      || a.recipe.recipe_id.localeCompare(b.recipe.recipe_id))
  const choice = candidates[0]
  if (!choice) return
  return {
    acceptanceId: createPlanId(), plan: choice.plan, language, source: 'blind_box',
    constraints: {
      ...constraints, scope: 'single_meal', meal_type: target, inferScope: false, onePerson: true,
      ingredient_mode: constraints?.ingredient_mode ?? 'flexible',
      cooking_time_limit: options.quick ? maxMinutes : constraints?.cooking_time_limit,
    },
  }
}
