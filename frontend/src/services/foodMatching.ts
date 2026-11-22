import { requestJson } from './apiClient'
import { foodStates } from './foodLogs'
import type { FoodItem, FoodState } from './foodLogs'

export type MatchingEntry = { item: FoodItem; identity_uncertain: boolean }

const identityStatuses = ['matched', 'ambiguous_identity', 'food_state_unknown', 'unsupported_food', 'insufficient_information'] as const
const portionStatuses = ['edible_mass', 'verified_conversion', 'quantity_unknown', 'conversion_unavailable', 'needs_review'] as const
export type Candidate = {
  food_id: string
  names: { zh_cn: string; en_us: string }
  state: FoodState
}
type MatchingResult = {
  reference_version: string
  requires_edible_weight_confirmation: boolean
  original: string
  identity_status: (typeof identityStatuses)[number]
  portion_status: (typeof portionStatuses)[number]
  reference: Candidate | null
  candidates: Candidate[]
  clarification: string | null
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function candidate(value: unknown): value is Candidate {
  return record(value) && typeof value.food_id === 'string'
    && record(value.names) && typeof value.names.zh_cn === 'string' && typeof value.names.en_us === 'string'
    && foodStates.some((state) => state === value.state)
}

function result(value: unknown): value is MatchingResult {
  return record(value) && typeof value.original === 'string' && identityStatuses.some((status) => status === value.identity_status)
    && typeof value.reference_version === 'string' && value.reference_version.length > 0
    && typeof value.requires_edible_weight_confirmation === 'boolean'
    && portionStatuses.some((status) => status === value.portion_status)
    && (value.clarification === null || typeof value.clarification === 'string')
    && (value.identity_status === 'matched' ? candidate(value.reference) : value.reference === null)
    && Array.isArray(value.candidates) && value.candidates.every(candidate)
}

export function previewFoodMatching(items: MatchingEntry[], signal: AbortSignal): Promise<MatchingResult[]> {
  return requestJson('/api/v1/food-normalization/preview', (data) => {
    if (Array.isArray(data) && data.length === items.length && data.every(result)
      && data.every((entry, index) => entry.original === items[index].item.name)) return data
    throw new Error('Invalid food matching preview')
  }, { body: { items }, signal, timeoutMs: 5_000, redirect: 'error' })
}
