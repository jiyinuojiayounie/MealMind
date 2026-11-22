import { requestJson } from './apiClient'
import { isMeal, mealTypes, parseMealPlan } from './mealPlans'
import type { MealPlan, MealType, PlannedMeal, PlanningMode } from './mealPlans'

type Context = {
  date: string
  context_fingerprint: string
  confirmed_log_count: number
  confirmed_by_meal_type: Record<MealType, number>
  unspecified_log_count: number
  locked_meal_types: MealType[]
  remaining_main_meal_types: MealType[]
}

export type ReplanContext = Context
export type ReplanRequest = {
  date: string
  timezone: string
  target_meal_type: MealType
  expected_context_fingerprint: string
  current_plan?: { plan_id: string; revision: number; date: string; source: PlanningMode; plan: MealPlan }
  planning_mode: PlanningMode
  constraints: {
    language: 'zh-CN' | 'en-US'
    ingredient_mode: 'existing' | 'flexible'
    available_ingredients: string[]
    cooking_time_limit?: number
    prefer_low_effort: boolean
    one_person: boolean
    restriction_status: 'none_declared'
  }
  instructions: string
}

export type ReplanPreview = {
  proposal_id: string
  current_meal: PlannedMeal | null
  suggested_plan: MealPlan
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function count(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
}

function isSlot(value: unknown): value is MealType {
  return mealTypes.some((type) => value === type)
}

function slots(value: unknown): value is MealType[] {
  return Array.isArray(value) && value.every(isSlot) && new Set(value).size === value.length
}

function parseContext(value: unknown, date: string): Context {
  if (!isRecord(value) || value.date !== date || value.date_basis !== 'recorded_offset' || value.day_completeness !== 'not_assessed'
    || typeof value.context_fingerprint !== 'string' || !/^[a-f0-9]{64}$/.test(value.context_fingerprint)
    || !count(value.confirmed_log_count) || !count(value.unspecified_log_count) || !isRecord(value.confirmed_by_meal_type)
    || !slots(value.locked_meal_types) || !slots(value.remaining_main_meal_types)
    || value.remaining_main_meal_types.includes('snack')) throw new Error('Invalid replan context')
  const counts = value.confirmed_by_meal_type
  if (!mealTypes.every((slot) => count(counts[slot]))) throw new Error('Invalid meal counts')
  const typedCounts = counts as Context['confirmed_by_meal_type']
  const locked = mealTypes.filter((slot) => typedCounts[slot] > 0)
  const main = mealTypes.filter((slot) => slot !== 'snack')
  const last = main.map((slot) => typedCounts[slot] > 0).lastIndexOf(true)
  if (mealTypes.reduce((total, slot) => total + typedCounts[slot], value.unspecified_log_count) !== value.confirmed_log_count
    || locked.join() !== value.locked_meal_types.join()
    || main.slice(last + 1).join() !== value.remaining_main_meal_types.join()) throw new Error('Inconsistent replan context')
  return {
    date, context_fingerprint: value.context_fingerprint, confirmed_log_count: value.confirmed_log_count,
    unspecified_log_count: value.unspecified_log_count, confirmed_by_meal_type: typedCounts,
    locked_meal_types: value.locked_meal_types, remaining_main_meal_types: value.remaining_main_meal_types,
  }
}

export function eligibleMeals(context: Context): MealType[] {
  return context.locked_meal_types.includes('snack')
    ? context.remaining_main_meal_types
    : [...context.remaining_main_meal_types, 'snack']
}

const options = { redirect: 'error', timeoutMs: 5_000 } as const

export function getReplanContext(date: string, signal?: AbortSignal) {
  return requestJson(`/api/v1/replan/context?date=${encodeURIComponent(date)}`, (value) => parseContext(value, date), {
    ...options, signal,
  })
}

export function getReplanPreview(request: ReplanRequest, signal: AbortSignal) {
  return requestJson('/api/v1/replan/preview', (value): ReplanPreview => {
    if (!isRecord(value) || value.status !== 'preview' || value.date !== request.date || value.timezone !== request.timezone
      || value.target_meal_type !== request.target_meal_type || value.source !== request.planning_mode
      || value.context_fingerprint !== request.expected_context_fingerprint
      || value.base_plan_id !== (request.current_plan?.plan_id ?? null)
      || value.base_plan_revision !== (request.current_plan?.revision ?? null)
      || typeof value.proposal_id !== 'string' || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(value.proposal_id)
      || !(value.current_meal === null || (isMeal(value.current_meal) && value.current_meal.meal_type === request.target_meal_type))) {
      throw new Error('Invalid replan preview')
    }
    const context = parseContext(value.context, request.date)
    const plan = parseMealPlan(value.suggested_plan)
    if (context.context_fingerprint !== request.expected_context_fingerprint
      || !eligibleMeals(context).includes(request.target_meal_type)
      || plan.meals.length !== 1 || plan.meals[0].meal_type !== request.target_meal_type) throw new Error('Invalid preview meal')
    return { proposal_id: value.proposal_id, current_meal: value.current_meal, suggested_plan: plan }
  }, { ...options, timeoutMs: 35_000, body: request, signal })
}
