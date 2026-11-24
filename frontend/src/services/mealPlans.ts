import { ApiError, requestJson } from './apiClient'

export const mealTypes = ['breakfast', 'lunch', 'dinner', 'snack'] as const
export type PlanningMode = 'prompt_only' | 'catalog'
export const catalogPreviewEnabled =
  import.meta.env.DEV && import.meta.env.VITE_CATALOG_PLANNING_PREVIEW === 'true'

export type MealType = (typeof mealTypes)[number]

export type MealPlanRequest = {
  user_request: string
  language: 'zh-CN' | 'en-US'
  scope: 'single_meal' | 'full_day'
  meal_type?: MealType
  available_ingredients?: string[]
  ingredient_mode: 'existing' | 'flexible'
  cooking_time_limit?: number
}

type Ingredient = { name: string; quantity: number; unit: string }
type Dish = { name: string; ingredients: Ingredient[]; instructions: string[] }
export type PlannedMeal = { meal_type: MealType; dishes: Dish[]; estimated_preparation_minutes: number }

export type MealPlan = {
  title: string
  meals: PlannedMeal[]
  explanation: string
  additional_ingredients: string[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isText(value: unknown): value is string {
  return typeof value === 'string' && value.trim() !== ''
}

function isIngredient(value: unknown): value is Ingredient {
  return isRecord(value) && isText(value.name) && isText(value.unit)
    && typeof value.quantity === 'number' && Number.isFinite(value.quantity) && value.quantity >= 0.001
}

function isDish(value: unknown): value is Dish {
  return isRecord(value) && isText(value.name)
    && Array.isArray(value.ingredients) && value.ingredients.length > 0 && value.ingredients.every(isIngredient)
    && Array.isArray(value.instructions) && value.instructions.length > 0 && value.instructions.every(isText)
}

export function isMeal(value: unknown): value is PlannedMeal {
  return isRecord(value) && mealTypes.some((type) => type === value.meal_type)
    && typeof value.estimated_preparation_minutes === 'number'
    && Number.isInteger(value.estimated_preparation_minutes) && value.estimated_preparation_minutes > 0
    && Array.isArray(value.dishes) && value.dishes.length > 0 && value.dishes.every(isDish)
}

export function parseMealPlan(value: unknown): MealPlan {
  if (isRecord(value) && isText(value.title) && isText(value.explanation)
    && Array.isArray(value.meals) && value.meals.length > 0 && value.meals.every(isMeal)
    && Array.isArray(value.additional_ingredients) && value.additional_ingredients.every(isText)) {
    return {
      title: value.title,
      explanation: value.explanation,
      meals: value.meals,
      additional_ingredients: value.additional_ingredients,
    }
  }
  throw new Error('Invalid meal plan response')
}

export function catalogOutcomeKey(error: unknown) {
  if (!(error instanceof ApiError) || !isRecord(error.detail)) return undefined
  const { status, reasons } = error.detail
  switch (status) {
    case 'no_feasible_plan': return 'catalogNoPlan'
    case 'clarification_required':
      return Array.isArray(reasons) && reasons.some(
        (reason) => reason === 'unconfirmed_allergies' || reason === 'unconfirmed_dietary_exclusions',
      ) ? 'catalogSafetyClarification' : 'catalogClarification'
    case 'unsupported_constraints': return 'catalogUnsupported'
    case 'catalog_disabled': return 'catalogDisabled'
    case 'draft_catalog_forbidden': return 'catalogLocalOnly'
    default: return undefined
  }
}

export function generateMealPlan(
  payload: MealPlanRequest, signal: AbortSignal, inferScope: boolean, mode: PlanningMode = 'prompt_only',
): Promise<MealPlan> {
  const query = new URLSearchParams()
  if (inferScope) query.set('infer_scope', 'true')
  if (catalogPreviewEnabled && mode === 'catalog') query.set('planning_mode', 'catalog')
  const path = '/api/v1/meal-plans/generate'
  // Original AI mode can wait for two 25-second provider attempts plus backoff.
  return requestJson(query.size ? `${path}?${query}` : path, parseMealPlan, {
    body: payload, signal, timeoutMs: mode === 'catalog' && catalogPreviewEnabled ? 35_000 : 55_000,
  })
}
