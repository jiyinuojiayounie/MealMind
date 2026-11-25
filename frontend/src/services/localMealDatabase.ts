export const planStore = 'plans'
export const foodLogStore = 'food-logs'

export function openLocalMealDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = window.indexedDB.open('mealmind-meal-plans', 2)
    let blocked = false
    request.onupgradeneeded = ({ oldVersion }) => {
      if (oldVersion < 1) request.result.createObjectStore(planStore, { keyPath: 'date' })
      const logs = request.result.createObjectStore(foodLogStore, { keyPath: 'id' })
      logs.createIndex('date', 'date')
    }
    request.onblocked = () => {
      blocked = true
      reject(new Error('Local meal database upgrade blocked'))
    }
    request.onerror = () => reject(new Error('Local meal database unavailable'))
    request.onsuccess = () => {
      const database = request.result
      database.onversionchange = () => database.close()
      if (blocked) database.close()
      else resolve(database)
    }
  })
}
