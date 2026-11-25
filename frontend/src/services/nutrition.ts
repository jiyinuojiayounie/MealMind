import { requestJson } from './apiClient'
import { logMealTypes } from './foodLogs'

export const nutrientKeys = ['energy_kcal', 'protein_g', 'carbohydrate_g', 'fat_g'] as const
export type NutrientKey = (typeof nutrientKeys)[number]
const coverageStates = ['no_confirmed_logs', 'not_calculable', 'partial', 'all_logged_items_calculated'] as const

export type NutrientSubtotal = {
  unit: 'kcal' | 'g'
  subtotal: string | null
  contributing_items: number
  missing_items: number
}

export type NutritionSummary = {
  item_count: number
  calculated_item_count: number
  fully_calculated_item_count: number
  uncalculated_item_count: number
  nutrients: Record<NutrientKey, NutrientSubtotal>
}

export type NutritionItem = {
  item_index: number
  name: string
  reasons: string[]
  conversion: 'edible_mass' | 'reference_portion' | null
  nutrients: Record<NutrientKey, string | null>
  provenance: {
    fdc_id: number
    food_id?: string
    state?: string
    nutrient_source_row_ids?: Partial<Record<NutrientKey, number>>
    portion_source_row_id?: number
  } | null
}

export type NutritionLog = {
  log_id: string
  meal_type: (typeof logMealTypes)[number]
  consumed_at: string
  summary: NutritionSummary
  items: NutritionItem[]
}

export type DailyNutrition = NutritionSummary & {
  date: string
  date_basis: 'recorded_offset'
  status: (typeof coverageStates)[number]
  day_completeness: 'not_assessed'
  confirmed_log_count: number
  logs: NutritionLog[]
  reference_version: string
  reference_source: { release: string }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
}

function isEstimate(value: unknown): value is string | null {
  if (value === null) return true
  if (typeof value !== 'string' || !/^\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i.test(value)) return false
  const number = Number(value)
  // A positive decimal outside the representable range must never display as zero.
  return Number.isFinite(number) && (number !== 0 || !/[1-9]/.test(value.split(/e/i)[0]))
}

function isSummary(value: unknown): value is NutritionSummary & Record<string, unknown> {
  if (!isRecord(value) || !isCount(value.item_count) || !isCount(value.calculated_item_count)
    || !isCount(value.fully_calculated_item_count) || !isCount(value.uncalculated_item_count)
    || value.fully_calculated_item_count > value.calculated_item_count
    || value.calculated_item_count + value.uncalculated_item_count !== value.item_count
    || !isRecord(value.nutrients)) return false
  const nutrients = value.nutrients
  return nutrientKeys.every((key) => {
    const entry = nutrients[key]
    return isRecord(entry) && entry.unit === (key === 'energy_kcal' ? 'kcal' : 'g')
      && isEstimate(entry.subtotal) && isCount(entry.contributing_items) && isCount(entry.missing_items)
      && entry.contributing_items + entry.missing_items === value.item_count
      && (entry.subtotal === null) === (entry.contributing_items === 0)
  })
}

function isItem(value: unknown, index: number): value is NutritionItem {
  if (!isRecord(value) || value.item_index !== index || typeof value.name !== 'string' || !value.name.trim()
    || !Array.isArray(value.reasons) || !value.reasons.every((reason: unknown) => typeof reason === 'string')
    || !isRecord(value.nutrients)
    || !(value.conversion === null || value.conversion === 'edible_mass' || value.conversion === 'reference_portion')
    || !(value.provenance === null || (isRecord(value.provenance)
      && isCount(value.provenance.fdc_id) && value.provenance.fdc_id > 0))) return false
  const nutrients = value.nutrients
  return nutrientKeys.every((key) => isEstimate(nutrients[key]))
}

function isLog(value: unknown, date: string): value is NutritionLog {
  return isRecord(value) && typeof value.log_id === 'string' && value.log_id.length > 0
    && logMealTypes.some((type) => type === value.meal_type)
    && typeof value.consumed_at === 'string' && value.consumed_at.startsWith(date + 'T')
    && /(?:Z|[+-]\d{2}:\d{2})$/.test(value.consumed_at) && Number.isFinite(Date.parse(value.consumed_at))
    && isSummary(value.summary) && Array.isArray(value.items) && value.items.length > 0
    && value.items.length === value.summary.item_count && value.items.every(isItem)
}

function parseDailyNutrition(value: unknown, date: string): DailyNutrition {
  if (!isSummary(value) || value.date !== date || value.date_basis !== 'recorded_offset'
    || value.day_completeness !== 'not_assessed' || !isCount(value.confirmed_log_count)
    || typeof value.reference_version !== 'string' || !isRecord(value.reference_source)
    || typeof value.reference_source.release !== 'string' || !Array.isArray(value.logs)
    || value.logs.length !== value.confirmed_log_count
    || !value.logs.every((log: unknown): log is NutritionLog => isLog(log, date))) {
    throw new Error('Invalid daily nutrition response')
  }
  const status = value.confirmed_log_count === 0 ? 'no_confirmed_logs'
    : value.calculated_item_count === 0 ? 'not_calculable'
      : value.fully_calculated_item_count === value.item_count ? 'all_logged_items_calculated' : 'partial'
  if (value.status !== status
    || new Set(value.logs.map((log) => log.log_id)).size !== value.logs.length
    || value.logs.reduce((count, log) => count + log.summary.item_count, 0) !== value.item_count) {
    throw new Error('Inconsistent daily nutrition coverage')
  }
  return value as DailyNutrition
}

export function getDailyNutrition(date: string, signal: AbortSignal) {
  const query = new URLSearchParams({ date })
  return requestJson(`/api/v1/nutrition/daily?${query}`, (data) => parseDailyNutrition(data, date), {
    signal, timeoutMs: 5_000, redirect: 'error',
  })
}
