import { ApiError } from './apiClient'
import { isItem, isLog, logMealTypes } from './foodLogs'
import type { FoodLog, FoodLogDraft } from './foodLogs'
import { foodLogStore, openLocalMealDatabase } from './localMealDatabase'

type LocalRecord = FoodLog & { date: string }

function readRecord(value: unknown): LocalRecord {
  if (!isLog(value) || value.source !== 'manual_text' || !('date' in value)
    || value.date !== value.consumed_at.slice(0, 10)) throw new ApiError(503)
  return value as LocalRecord
}

async function transact<F, T>(
  mode: IDBTransactionMode, read: (store: IDBObjectStore) => IDBRequest<F>,
  finish: (value: F, store: IDBObjectStore) => T,
): Promise<T> {
  let db: IDBDatabase | undefined
  try {
    db = await openLocalMealDatabase()
    const opened = db
    return await new Promise<T>((resolve, reject) => {
      const tx = opened.transaction(foodLogStore, mode)
      const store = tx.objectStore(foodLogStore)
      const request = read(store)
      let result: T
      let error: unknown
      request.onsuccess = () => {
        try { result = finish(request.result, store) } catch (failure) {
          error = failure
          tx.abort()
        }
      }
      tx.oncomplete = () => resolve(result)
      tx.onabort = () => reject(error ?? new ApiError(503))
    })
  } catch (error) {
    throw error instanceof ApiError ? error : new ApiError(503)
  } finally {
    db?.close()
  }
}

export function readLocalFoodLogs(store: IDBObjectStore, date: string) {
  return store.index('date').getAll(date)
}

export function confirmedLocalRecords(values: unknown[]) {
  return values.map(readRecord).filter((log) => log.status === 'confirmed')
}

export function confirmedMealSlots(values: unknown[]) {
  return new Set(confirmedLocalRecords(values).map((log) => log.meal_type))
}

export function confirmedLogFingerprint(values: unknown[]) {
  return JSON.stringify(confirmedLocalRecords(values).map(({ id, revision }) => `${id}:${revision}`).sort())
}

export function listLocalFoodLogs(date: string) {
  return transact('readonly', (store) => readLocalFoodLogs(store, date), (records) =>
    records.map(readRecord).sort((a, b) => b.consumed_at.localeCompare(a.consumed_at) || a.id.localeCompare(b.id)))
}

function currentRecord(value: unknown, expected: FoodLog): LocalRecord {
  if (value === undefined) throw new ApiError(409)
  const current = readRecord(value)
  if (current.revision !== expected.revision) throw new ApiError(409)
  return current
}

export function saveLocalFoodLog(draft: FoodLogDraft, expected: FoodLog | null, creationId: string) {
  const items = draft.items.map(({ name, quantity, unit, preparation_method }) => ({ name, quantity, unit, preparation_method }))
  const now = new Date().toISOString()
  const id = expected?.id ?? creationId
  if (!logMealTypes.includes(draft.meal_type) || !items.length || items.length > 50 || !items.every(isItem)
    || (draft.description !== null && Array.from(draft.description).length > 2000)) throw new ApiError(422)
  return transact('readwrite', (store) => store.get(id), (value, store) => {
    if (!expected && value !== undefined) {
      const existing = readRecord(value)
      if (existing.status !== 'draft' || existing.revision !== 1 || existing.description !== draft.description
        || existing.consumed_at !== draft.consumed_at || existing.meal_type !== draft.meal_type
        || JSON.stringify(existing.items) !== JSON.stringify(items)) throw new ApiError(409)
      return existing
    }
    const current = expected ? currentRecord(value, expected) : undefined
    const next: LocalRecord = {
      ...draft, id, items, date: draft.consumed_at.slice(0, 10), source: 'manual_text',
      status: current?.status ?? 'draft', revision: (current?.revision ?? 0) + 1,
      created_at: current?.created_at ?? now, updated_at: now,
    }
    if (!isLog(next)) throw new ApiError(422)
    if (current) store.put(next)
    else store.add(next)
    return next
  })
}

export function confirmLocalFoodLog(expected: FoodLog) {
  return transact('readwrite', (store) => store.get(expected.id), (value, store) => {
    if (value !== undefined) {
      const latest = readRecord(value)
      if (latest.status === 'confirmed' && expected.status === 'draft' && latest.revision === expected.revision + 1) return latest
    }
    const current = currentRecord(value, expected)
    if (current.status === 'confirmed') return current
    const next: LocalRecord = {
      ...current, status: 'confirmed', revision: current.revision + 1, updated_at: new Date().toISOString(),
    }
    store.put(next)
    return next
  })
}

export function deleteLocalFoodLog(expected: FoodLog) {
  return transact('readwrite', (store) => store.get(expected.id), (value, store) => {
    currentRecord(value, expected)
    store.delete(expected.id)
  })
}
