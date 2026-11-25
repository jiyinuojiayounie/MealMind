import reference from '../../../data/nutrition/reference-v1.json'
import rules from '../../../data/nutrition/browser-rules-v1.json'
import type { FoodLog } from './foodLogs'
import { listLocalFoodLogs } from './localFoodLogRepository'
import { nutrientKeys } from './nutrition'
import type { DailyNutrition, NutrientKey, NutritionItem, NutritionSummary } from './nutrition'

type FoodReference = {
  food_id: string
  names: { zh_cn: string; en_us: string }
  aliases: string[]
  state: string
  preparation: string
  source: { fdc_id: number }
  nutrients: Record<NutrientKey, { amount: number; source_row_id: number } | null>
  portions?: { source_row_id: number; amount: number; edible_grams: number }[]
}

type Reference = Pick<typeof reference, 'reference_version' | 'source' | 'unresolved_labels'> & {
  foods: FoodReference[]
}
type LogItem = FoodLog['items'][number]

function normalize(label: string) {
  return label.normalize('NFKC').toLowerCase().trim().replace(/\s+/gu, ' ')
}

const preparations = new Map(Object.entries(rules.preparations))
const states = new Set(rules.states)
const qualified = new Map<string, Record<string, string>>(Object.entries(rules.qualified_foods))
const unspecified = new Set(rules.unspecified_state)
const mixed = new Set(rules.mixed_dishes)
const mass = new Map(Object.entries(rules.mass_factors))
const household = new Set(rules.household_units)
const portions = new Map<string, Record<string, number>>(Object.entries(rules.portion_units))

export function createLocalNutritionCalculator(dataset: Reference = reference) {
  const byId = new Map(dataset.foods.map((food) => [food.food_id, food]))
  const byLabel = new Map(dataset.foods.flatMap((food) =>
    [food.names.zh_cn, food.names.en_us, ...food.aliases].map((label) => [normalize(label), food] as const)))
  const unresolved = new Set(dataset.unresolved_labels.map(normalize))

  function match(item: LogItem): [FoodReference | null, string?] {
    if (item.reference_binding != null) return [null, 'food_reference_binding_invalid']
    const label = normalize(item.name)
    const preparation = normalize(item.preparation_method ?? '')
    const method = preparations.get(preparation)
    const food = byLabel.get(label)
    if (food) {
      if (!preparation || food.state === method
        || (method && !states.has(method) && food.state === 'cooked'
          && new RegExp(`\\b${method}\\b`, 'i').test(food.preparation))) return [food]
      return [null, 'food_preparation_mismatch']
    }
    const variants = qualified.get(label)
    if (variants) {
      if (!preparation) return [null, 'food_state_unknown']
      const exact = method ? byId.get(variants[method]) : undefined
      if (exact) return [exact]
      const compatible = method ? Object.values(variants).filter((id) => byId.get(id)?.state === method) : []
      return [null, compatible.length > 1 ? 'ambiguous_food_match' : 'food_preparation_mismatch']
    }
    if (mixed.has(label)) return [null, 'mixed_dish_unsupported']
    if (unspecified.has(label) && !preparation) return [null, 'food_state_unknown']
    if (unresolved.has(label) || unspecified.has(label)) return [null, 'ambiguous_food_match']
    return [null, 'food_not_found']
  }

  function calculateItem(item: LogItem, index: number, reviewWeight = false): NutritionItem {
    const [food, issue] = match(item)
    const result: NutritionItem = {
      name: item.name, item_index: index, reasons: issue ? [issue] : [], conversion: null,
      nutrients: { energy_kcal: null, protein_g: null, carbohydrate_g: null, fat_g: null },
      provenance: food ? {
        fdc_id: food.source.fdc_id, food_id: food.food_id, state: food.state,
        nutrient_source_row_ids: Object.fromEntries(nutrientKeys.flatMap((key) => {
          const value = food.nutrients[key]
          return value ? [[key, value.source_row_id]] : []
        })),
      } : null,
    }
    const skip = (reason: string) => {
      result.reasons.push(reason)
      return result
    }
    const quantity = item.quantity
    if (quantity === null) return skip('quantity_unknown')
    if (!Number.isFinite(quantity) || quantity <= 0) return skip('invalid_quantity')
    if (!food) return result
    const unit = normalize(item.unit ?? '')
    const factor = mass.get(unit)
    const foodPortions = portions.get(unit)
    let grams: number
    let conversion: NutritionItem['conversion']
    let portionRow: number | undefined
    if (factor !== undefined) {
      if (reviewWeight) return skip('portion_needs_review')
      grams = quantity * factor
      conversion = 'edible_mass'
    } else if (household.has(unit) || foodPortions) {
      const portion = food.portions?.find((row) => row.source_row_id === foodPortions?.[food.food_id])
      if (!portion) return skip('unsupported_serving_conversion')
      grams = quantity * portion.edible_grams / portion.amount
      conversion = 'reference_portion'
      portionRow = portion.source_row_id
    } else {
      return skip('unsupported_unit')
    }
    if (!Number.isFinite(grams) || grams <= 0 || grams > rules.max_edible_grams) return skip('portion_needs_review')
    const estimates = nutrientKeys.map((key) => {
      const nutrient = food.nutrients[key]
      return nutrient === null ? null : nutrient.amount * grams / 100
    })
    if (estimates.some((value, i) => value === 0 && food.nutrients[nutrientKeys[i]]?.amount !== 0)) {
      return skip('portion_needs_review')
    }
    for (const [index, key] of nutrientKeys.entries()) {
      const value = estimates[index]
      result.nutrients[key] = value === null ? null : String(value)
    }
    if (estimates.includes(null)) result.reasons.push('nutrient_data_missing')
    result.conversion = conversion
    if (result.provenance && portionRow !== undefined) result.provenance.portion_source_row_id = portionRow
    return result
  }

  return { calculateItem }
}

export function summarizeLocalNutrition(items: NutritionItem[]): NutritionSummary {
  const calculated = items.filter((item) => nutrientKeys.some((key) => item.nutrients[key] !== null))
  const nutrients = {} as NutritionSummary['nutrients']
  for (const key of nutrientKeys) {
    const values = calculated.flatMap((item) => item.nutrients[key] === null ? [] : [Number(item.nutrients[key])])
    nutrients[key] = {
      unit: key === 'energy_kcal' ? 'kcal' : 'g',
      subtotal: values.length ? String(values.reduce((sum, value) => sum + value, 0)) : null,
      contributing_items: values.length, missing_items: items.length - values.length,
    }
  }
  return {
    item_count: items.length, calculated_item_count: calculated.length,
    fully_calculated_item_count: calculated.filter((item) => !item.reasons.length).length,
    uncalculated_item_count: items.length - calculated.length, nutrients,
  }
}

const calculator = createLocalNutritionCalculator()

export function analyzeLocalNutrition(date: string, records: FoodLog[]): DailyNutrition {
  const seen = new Set<string>()
  const logs = records.flatMap((log) => {
    if (log.status !== 'confirmed' || log.consumed_at.slice(0, 10) !== date || seen.has(log.id)) return []
    seen.add(log.id)
    const items = log.items.map((item, index) => calculator.calculateItem(item, index, log.recognition_weight_review))
    return [{
      log_id: log.id, meal_type: log.meal_type, consumed_at: log.consumed_at,
      items, summary: summarizeLocalNutrition(items),
    }]
  })
  const summary = summarizeLocalNutrition(logs.flatMap((log) => log.items))
  return {
    ...summary, logs, date, date_basis: 'recorded_offset', day_completeness: 'not_assessed',
    confirmed_log_count: logs.length,
    reference_version: reference.reference_version, reference_source: reference.source,
    status: !logs.length ? 'no_confirmed_logs' : !summary.calculated_item_count ? 'not_calculable'
      : summary.fully_calculated_item_count === summary.item_count ? 'all_logged_items_calculated' : 'partial',
  }
}

export async function getLocalNutrition(date: string) {
  return analyzeLocalNutrition(date, await listLocalFoodLogs(date))
}
