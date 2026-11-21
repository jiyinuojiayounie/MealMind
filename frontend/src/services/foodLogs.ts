import { apiBaseUrl, requestJson } from './apiClient'
import { mealTypes } from './mealPlans'

export const logMealTypes = ['unspecified', ...mealTypes] as const

export type FoodItem = {
  name: string
  quantity: number | null
  unit: string | null
  preparation_method: string | null
}

export type FoodLogDraft = {
  meal_type: (typeof logMealTypes)[number]
  consumed_at: string
  description: string
  items: FoodItem[]
}

export type FoodLogSource = 'manual_text' | 'ai_text' | 'ai_image'
export type RecognitionSource = Exclude<FoodLogSource, 'manual_text'>
export type PortionNote = 'quantity_unspecified' | 'portion_needs_review' | null
type RecognitionNote = 'no_identifiable_foods' | 'description_needs_review'

type RecognizedItem = FoodItem & { portion_note: PortionNote; identity_uncertain?: boolean }

export type FoodRecognition = ({
  source: 'ai_text'
  description: string
  notes: RecognitionNote[]
} | {
  source: 'ai_image'
  description: null
  notes: ('no_identifiable_foods' | 'image_needs_review')[]
}) & {
  items: RecognizedItem[]
}

export type FoodLog = FoodLogDraft & {
  id: string
  source: FoodLogSource
  status: 'draft' | 'confirmed'
  revision: number
  created_at: string
  updated_at: string
}

function isLoopback(host: string) {
  return ['localhost', '127.0.0.1', '[::1]'].includes(host)
}

export function canUseFoodLogs(): boolean {
  if (!import.meta.env.DEV || !isLoopback(window.location.hostname)) return false
  try {
    const url = new URL(apiBaseUrl)
    return (url.protocol === 'http:' || url.protocol === 'https:') && isLoopback(url.hostname)
      && !url.username && !url.password && !url.search && !url.hash
  } catch {
    return false
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isItem(value: unknown): value is FoodItem {
  return isRecord(value) && isShortText(value.name)
    && (value.quantity === null || (typeof value.quantity === 'number' && Number.isFinite(value.quantity) && value.quantity > 0))
    && (value.unit === null || isShortText(value.unit))
    && (value.preparation_method === null || isShortText(value.preparation_method))
}

function isShortText(value: unknown): value is string {
  return typeof value === 'string' && value.trim() !== '' && Array.from(value).length <= 120
}

function isRecognizedItem(value: unknown): value is RecognizedItem {
  return isRecord(value) && (value.portion_note === null || value.portion_note === 'quantity_unspecified'
    || value.portion_note === 'portion_needs_review') && isItem(value)
}

function isRecognitionNote(value: unknown): value is RecognitionNote {
  return value === 'no_identifiable_foods' || value === 'description_needs_review'
}

function isTimestamp(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value))
}

function isLog(value: unknown): value is FoodLog {
  return isRecord(value) && typeof value.id === 'string'
    && logMealTypes.some((type) => type === value.meal_type)
    && (value.status === 'draft' || value.status === 'confirmed')
    && (value.source === 'manual_text' || value.source === 'ai_text' || value.source === 'ai_image')
    && typeof value.revision === 'number' && Number.isSafeInteger(value.revision) && value.revision > 0
    && typeof value.description === 'string' && isTimestamp(value.consumed_at)
    && isTimestamp(value.created_at) && isTimestamp(value.updated_at)
    && Array.isArray(value.items) && value.items.length > 0 && value.items.every(isItem)
}

function parseLog(value: unknown): FoodLog {
  if (isLog(value)) return value
  throw new Error('Invalid food log response')
}

const path = '/api/v1/food-logs'
const options = { timeoutMs: 5_000, redirect: 'error' } as const

export function recognizeFoodText(description: string, signal: AbortSignal): Promise<FoodRecognition> {
  return requestJson(`${path}/recognize-text`, (value) => {
    if (isRecord(value) && value.description === description && value.source === 'ai_text' && value.status === 'draft'
      && Array.isArray(value.items) && value.items.length <= 50 && value.items.every(isRecognizedItem)
      && Array.isArray(value.notes) && value.notes.every(isRecognitionNote)) {
      return { source: 'ai_text', description, items: value.items, notes: value.notes }
    }
    throw new Error('Invalid food recognition proposal')
  }, { ...options, timeoutMs: 35_000, body: { description }, signal })
}

export const maxFoodPhotoBytes = 5 * 1024 * 1024

export function recognizeFoodImage(image: File, signal: AbortSignal): Promise<FoodRecognition> {
  const body = new FormData()
  body.append('image', image)
  return requestJson(`${path}/recognize-image`, (value) => {
    if (isRecord(value) && value.description === null && value.source === 'ai_image' && value.status === 'draft'
      && Array.isArray(value.items) && value.items.length <= 50 && value.items.every(
        (item: unknown) => isRecognizedItem(item) && typeof item.identity_uncertain === 'boolean',
      ) && Array.isArray(value.notes) && value.notes.every(
        (note: unknown) => note === 'no_identifiable_foods' || note === 'image_needs_review',
      )) {
      return { source: 'ai_image', description: null, items: value.items, notes: value.notes }
    }
    throw new Error('Invalid food image recognition proposal')
  }, { ...options, timeoutMs: 35_000, body, signal })
}

export function listFoodLogs(date: string, signal: AbortSignal): Promise<FoodLog[]> {
  return requestJson(`${path}?date=${encodeURIComponent(date)}`, (value) => {
    if (Array.isArray(value) && value.every(isLog)) return value
    throw new Error('Invalid food log list')
  }, { ...options, signal })
}

export function saveFoodLog(
  draft: FoodLogDraft, existing: FoodLog | null, source: FoodLogSource, signal: AbortSignal,
) {
  if (existing) {
    return requestJson(`${path}/${encodeURIComponent(existing.id)}`, parseLog, {
      ...options, method: 'PUT', body: { ...draft, expected_revision: existing.revision }, signal,
    })
  }
  return requestJson(path, parseLog, { ...options, body: { ...draft, source }, signal })
}

export function confirmFoodLog(log: FoodLog, signal: AbortSignal) {
  return requestJson(`${path}/${encodeURIComponent(log.id)}/confirm`, parseLog, {
    ...options, body: { expected_revision: log.revision }, signal,
  })
}

export function deleteFoodLog(log: FoodLog, signal: AbortSignal) {
  return requestJson(`${path}/${encodeURIComponent(log.id)}?expected_revision=${log.revision}`, (value) => {
    if (value !== undefined) throw new Error('Invalid food log deletion response')
  }, { ...options, method: 'DELETE', signal })
}
