import { postJson } from './apiClient'

export const mealTypes = ['breakfast', 'lunch', 'dinner', 'snack'] as const
type MealType = (typeof mealTypes)[number]

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
type Meal = { meal_type: MealType; dishes: Dish[]; estimated_preparation_minutes: number }

export type MealPlan = {
  title: string
  meals: Meal[]
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

function isMeal(value: unknown): value is Meal {
  return isRecord(value) && mealTypes.some((type) => type === value.meal_type)
    && typeof value.estimated_preparation_minutes === 'number'
    && Number.isInteger(value.estimated_preparation_minutes) && value.estimated_preparation_minutes > 0
    && Array.isArray(value.dishes) && value.dishes.length > 0 && value.dishes.every(isDish)
}

function parseMealPlan(value: unknown): MealPlan {
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

export function generateMealPlan(payload: MealPlanRequest, signal: AbortSignal): Promise<MealPlan> {
  return postJson('/api/v1/meal-plans/generate', payload, parseMealPlan, signal)
}
