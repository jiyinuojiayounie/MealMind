import { mealTypes, parseMealPlan } from './mealPlans'
import type { MealPlan, MealPlanRequest, MealType, PlanningMode } from './mealPlans'

import { foodLogStore, openLocalMealDatabase, planStore } from './localMealDatabase'
import { confirmedLocalRecords, confirmedLogFingerprint, confirmedMealSlots, readLocalFoodLogs } from './localFoodLogRepository'

const schemaVersion = 1

export type PlanConstraints = Pick<MealPlanRequest,
  'scope' | 'meal_type' | 'ingredient_mode' | 'available_ingredients' | 'cooking_time_limit'> & {
  inferScope: boolean
  onePerson?: boolean
  preferLowEffort?: boolean
}

export type PlanSource = PlanningMode | 'blind_box'

type PlanSettings = {
  language: MealPlanRequest['language']
  source: PlanSource
  constraints: PlanConstraints
}

export type PlanAcceptance = PlanSettings & {
  acceptanceId: string
  plan: MealPlan
  slotSettings?: Partial<Record<MealType, PlanSettings>>
}

export type PlanRevision = PlanAcceptance & { revision: number; savedAt: string }
export type PlanIdentity = { planId: string; revision: number; lockRevision?: number }

export type SavedMealPlan = PlanIdentity & {
  schemaVersion: typeof schemaVersion
  date: string
  revisions: PlanRevision[]
  lockedMealTypes?: MealType[]
}

export class PlanStorageError extends Error {
  readonly code: 'unavailable' | 'invalid' | 'stale' | 'locked'

  constructor(code: PlanStorageError['code']) {
    super(`Meal plan storage: ${code}`)
    this.code = code
  }
}

export function createPlanId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-')
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isId(value: unknown): value is string {
  return typeof value === 'string' && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(value)
}

function isPlanDate(date: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date)
  if (!match) return false
  const [year, month, day] = match.slice(1).map(Number)
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
  return year > 0 && month >= 1 && month <= 12 && day >= 1 && day <= days[month - 1]
}

function parseConstraints(value: unknown): PlanConstraints {
  if (!isObject(value) || (value.scope !== 'single_meal' && value.scope !== 'full_day')
    || (value.ingredient_mode !== 'existing' && value.ingredient_mode !== 'flexible') || typeof value.inferScope !== 'boolean'
    || (value.onePerson !== undefined && typeof value.onePerson !== 'boolean')
    || (value.preferLowEffort !== undefined && typeof value.preferLowEffort !== 'boolean')
    || (value.meal_type !== undefined && (!mealTypes.some((type) => value.meal_type === type) || value.scope === 'full_day'))
    || (value.available_ingredients !== undefined && (!Array.isArray(value.available_ingredients)
      || value.available_ingredients.length > 60 || !value.available_ingredients.every(
        (item: unknown) => typeof item === 'string' && item.trim() && Array.from(item).length <= 120,
      )))
    || (value.ingredient_mode === 'existing' && !(value.available_ingredients as string[] | undefined)?.length)
    || (value.cooking_time_limit !== undefined && (typeof value.cooking_time_limit !== 'number'
      || !Number.isInteger(value.cooking_time_limit) || value.cooking_time_limit < 1 || value.cooking_time_limit > 480))) {
    throw new PlanStorageError('invalid')
  }
  return {
    scope: value.scope, ingredient_mode: value.ingredient_mode, inferScope: value.inferScope,
    meal_type: mealTypes.find((type) => type === value.meal_type),
    available_ingredients: value.available_ingredients as string[] | undefined,
    cooking_time_limit: value.cooking_time_limit,
    ...(value.onePerson !== undefined && { onePerson: value.onePerson }),
    ...(value.preferLowEffort !== undefined && { preferLowEffort: value.preferLowEffort }),
  }
}

function parseSettings(value: unknown): PlanSettings {
  if (!isObject(value) || (value.language !== 'zh-CN' && value.language !== 'en-US')
    || (value.source !== 'prompt_only' && value.source !== 'catalog' && value.source !== 'blind_box')) throw new PlanStorageError('invalid')
  return { language: value.language, source: value.source, constraints: parseConstraints(value.constraints) }
}

function parseAcceptance(value: unknown): PlanAcceptance {
  if (!isObject(value) || !isId(value.acceptanceId)) throw new PlanStorageError('invalid')
  const settings = parseSettings(value)
  let plan: MealPlan
  try {
    plan = parseMealPlan(value.plan)
  } catch {
    throw new PlanStorageError('invalid')
  }
  if (new Set(plan.meals.map((meal) => meal.meal_type)).size !== plan.meals.length) throw new PlanStorageError('invalid')
  let slotSettings
  if (value.slotSettings !== undefined) {
    if (!isObject(value.slotSettings)) throw new PlanStorageError('invalid')
    slotSettings = Object.fromEntries(Object.entries(value.slotSettings).map(([slot, details]) => {
      if (!plan.meals.some((meal) => meal.meal_type === slot)) throw new PlanStorageError('invalid')
      return [slot, parseSettings(details)]
    }))
  }
  return {
    ...settings, acceptanceId: value.acceptanceId, ...(slotSettings && { slotSettings }),
    plan: {
      ...plan,
      meals: plan.meals.map(({ meal_type, dishes, estimated_preparation_minutes }) => ({
        meal_type, estimated_preparation_minutes,
        dishes: dishes.map(({ name, ingredients, instructions }) => ({
          name, ingredients: ingredients.map(({ name, quantity, unit }) => ({ name, quantity, unit })), instructions,
        })),
      })),
    },
  }
}

function parseSavedPlan(value: unknown, date: string): SavedMealPlan {
  if (!isObject(value) || value.schemaVersion !== schemaVersion || value.date !== date || !isId(value.planId)
    || !Array.isArray(value.revisions) || value.revisions.length === 0 || value.revision !== value.revisions.length) {
    throw new PlanStorageError('invalid')
  }
  const ids = new Set<string>()
  const revisions = Array.from(value.revisions, (snapshot: unknown, index): PlanRevision => {
    if (!isObject(snapshot) || snapshot.revision !== index + 1 || typeof snapshot.savedAt !== 'string'
      || !Number.isFinite(Date.parse(snapshot.savedAt))) throw new PlanStorageError('invalid')
    const accepted = parseAcceptance(snapshot)
    if (ids.has(accepted.acceptanceId)) throw new PlanStorageError('invalid')
    ids.add(accepted.acceptanceId)
    return { ...accepted, revision: snapshot.revision, savedAt: snapshot.savedAt }
  })
  const saved: SavedMealPlan = { schemaVersion, date, planId: value.planId, revision: revisions.length, revisions }
  if (value.lockedMealTypes !== undefined || value.lockRevision !== undefined) {
    if (!Array.isArray(value.lockedMealTypes) || typeof value.lockRevision !== 'number'
      || !Number.isSafeInteger(value.lockRevision) || value.lockRevision < 1
      || new Set(value.lockedMealTypes).size !== value.lockedMealTypes.length
      || !value.lockedMealTypes.every((slot: unknown) => revisions.at(-1)?.plan.meals.some((meal) => meal.meal_type === slot))) {
      throw new PlanStorageError('invalid')
    }
    saved.lockedMealTypes = value.lockedMealTypes
    saved.lockRevision = value.lockRevision
  }
  return saved
}

async function withPlan<T>(
  date: string, mode: IDBTransactionMode,
  perform: (store: IDBObjectStore, current: SavedMealPlan | null, logs: unknown[]) => T,
  includeLogs = false,
) {
  if (!isPlanDate(date)) throw new PlanStorageError('invalid')
  let database: IDBDatabase | undefined
  try {
    database = await openLocalMealDatabase()
    const opened = database
    return await new Promise<T>((resolve, reject) => {
      const checkLocks = includeLogs || (import.meta.env.PROD && mode === 'readwrite')
      const transaction = opened.transaction(checkLocks ? [planStore, foodLogStore] : planStore, mode)
      const store = transaction.objectStore(planStore)
      const logs = checkLocks ? readLocalFoodLogs(transaction.objectStore(foodLogStore), date) : undefined
      const request = store.get(date)
      let result: T
      let error: unknown
      request.onsuccess = () => {
        try {
          const current = request.result === undefined ? null : parseSavedPlan(request.result, date)
          result = perform(store, current, logs?.result ?? [])
        } catch (failure) {
          error = failure
          transaction.abort()
        }
      }
      transaction.oncomplete = () => resolve(result)
      transaction.onabort = () => reject(error ?? new PlanStorageError('unavailable'))
    })
  } catch (error) {
    throw error instanceof PlanStorageError ? error : new PlanStorageError('unavailable')
  } finally {
    database?.close()
  }
}

export function getSavedMealPlan(date: string) {
  return withPlan(date, 'readonly', (_store, current) => current)
}

export function getLocalReplanSnapshot(date: string) {
  return withPlan(date, 'readonly', (_store, record, logs) => ({
    record, logs: confirmedLocalRecords(logs), fingerprint: confirmedLogFingerprint(logs),
  }), true)
}

function requirePlanVersion(current: SavedMealPlan | null, expected: PlanIdentity | null) {
  if ((current?.planId ?? null) !== (expected?.planId ?? null)
    || (current?.revision ?? null) !== (expected?.revision ?? null)
    || (current?.lockRevision ?? 0) !== (expected?.lockRevision ?? 0)) throw new PlanStorageError('stale')
}

export function savePlanLocks(date: string, expected: PlanIdentity, lockedMealTypes: MealType[]) {
  return withPlan(date, 'readwrite', (store, current) => {
    if (!current) throw new PlanStorageError('stale')
    requirePlanVersion(current, expected)
    const planned = current.revisions.at(-1)?.plan.meals ?? []
    if (lockedMealTypes.some((slot) => !planned.some((meal) => meal.meal_type === slot))) throw new PlanStorageError('invalid')
    const next = { ...current, lockedMealTypes: [...new Set(lockedMealTypes)], lockRevision: (current.lockRevision ?? 0) + 1 }
    store.put(next)
    return next
  })
}

export function settingsForMeal(snapshot: PlanAcceptance, slot: MealType): PlanSettings {
  return snapshot.slotSettings?.[slot] ?? parseSettings(snapshot)
}

function mergeMealSlots(current: PlanRevision | undefined, choice: PlanAcceptance): PlanAcceptance {
  if (!current) return choice
  const targeted = new Set(choice.plan.meals.map((meal) => meal.meal_type))
  const retained = current.plan.meals.filter((meal) => !targeted.has(meal.meal_type))
  if (!retained.length) return choice
  const allMeals = [...retained, ...choice.plan.meals].sort((a, b) => mealTypes.indexOf(a.meal_type) - mealTypes.indexOf(b.meal_type))
  const retainedNames = new Set(retained.flatMap((meal) => meal.dishes.flatMap((dish) =>
    dish.ingredients.map((ingredient) => ingredient.name))))
  return {
    ...choice,
    slotSettings: Object.fromEntries(allMeals.map((meal) => [
      meal.meal_type,
      settingsForMeal(targeted.has(meal.meal_type) ? choice : current, meal.meal_type),
    ])),
    plan: {
      ...choice.plan, title: current.plan.title, meals: allMeals,
      additional_ingredients: [...new Set([
        ...current.plan.additional_ingredients.filter((name) => retainedNames.has(name)),
        ...choice.plan.additional_ingredients,
      ])],
    },
  }
}

export function acceptMealPlan(date: string, choice: PlanAcceptance, expected: PlanIdentity | null, expectedLogs?: string) {
  return withPlan(date, 'readwrite', (store, current, logs) => {
    const accepted = parseAcceptance(choice)
    if (current?.revisions.some((version) => version.acceptanceId === accepted.acceptanceId)) return current
    requirePlanVersion(current, expected)
    if (expectedLogs !== undefined && confirmedLogFingerprint(logs) !== expectedLogs) throw new PlanStorageError('stale')
    const locked = confirmedMealSlots(logs)
    if (accepted.plan.meals.some((meal) => locked.has(meal.meal_type) || current?.lockedMealTypes?.includes(meal.meal_type))) {
      throw new PlanStorageError('locked')
    }
    const revision = (current?.revision ?? 0) + 1
    const merged = mergeMealSlots(current?.revisions.at(-1), accepted)
    const next: SavedMealPlan = {
      schemaVersion, date, planId: current?.planId ?? createPlanId(), revision,
      ...(current?.lockRevision !== undefined && { lockRevision: current.lockRevision, lockedMealTypes: current.lockedMealTypes }),
      revisions: [...(current?.revisions ?? []), { ...merged, revision, savedAt: new Date().toISOString() }],
    }
    store.put(next)
    return next
  })
}
