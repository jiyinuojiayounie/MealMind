export const apiBaseUrl = import.meta.env.DEV && import.meta.env.VITE_LAN_PREVIEW === '1' ? '' : (
  import.meta.env.VITE_API_BASE_URL?.trim() ||
  (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '')
).replace(/\/+$/, '')

export class ApiError extends Error {
  readonly status: number

  readonly detail: unknown

  constructor(status: number, detail?: unknown) {
    super(`API request failed with HTTP ${status}`)
    this.status = status
    this.detail = detail
  }
}

type JsonRequest = {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  body?: object
  redirect?: RequestRedirect
  signal?: AbortSignal
  timeoutMs: number
}

export function requestJson<T>(path: `/${string}`, parse: (data: unknown) => T, request: JsonRequest): Promise<T> {
  if (import.meta.env.PROD) return Promise.reject(new ApiError(403))
  return fetchJson(apiBaseUrl + path, parse, request)
}

const configuredPublicOrigin = import.meta.env.VITE_PUBLIC_PLANNING_API_ORIGIN?.trim()
const publicOrigin = (() => {
  if (!import.meta.env.PROD || import.meta.env.VITE_PUBLIC_PLANNING_ENABLED !== 'true' || !configuredPublicOrigin) return
  try {
    const url = new URL(configuredPublicOrigin)
    if (url.protocol === 'https:' && !url.username && !url.password && !url.search && !url.hash && url.pathname === '/') {
      return url.origin
    }
  } catch { /* An invalid origin leaves the public planner disabled. */ }
})()

export const publicPlanningEnabled = Boolean(publicOrigin)

export function requestPublicMealPlan<T>(
  body: object, parse: (value: unknown) => T, signal: AbortSignal, inferScope: boolean,
): Promise<T> {
  if (!publicOrigin) return Promise.reject(new ApiError(403))
  const path = '/api/v1/meal-plans/generate' + (inferScope ? '?infer_scope=true' : '')
  return fetchJson(publicOrigin + path, parse, { body, signal, timeoutMs: 35_000, redirect: 'error' })
}

async function fetchJson<T>(
  url: string,
  parse: (data: unknown) => T,
  { body, method = body ? 'POST' : 'GET', redirect, signal, timeoutMs }: JsonRequest,
): Promise<T> {
  const timeout = AbortSignal.timeout(timeoutMs)
  const multipart = body instanceof FormData
  const response = await fetch(url, {
    method,
    headers: body && !multipart
      ? { Accept: 'application/json', 'Content-Type': 'application/json' }
      : { Accept: 'application/json' },
    body: multipart ? body : body ? JSON.stringify(body) : undefined,
    credentials: 'omit',
    cache: 'no-store',
    redirect,
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  })

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => undefined)
    const detail = typeof body === 'object' && body !== null && 'detail' in body ? body.detail : undefined
    throw new ApiError(response.status, detail)
  }
  return parse(response.status === 204 ? undefined : await response.json())
}

export function getJson<T>(
  path: `/${string}`,
  parse: (data: unknown) => T,
  signal?: AbortSignal,
): Promise<T> {
  return requestJson(path, parse, { signal, timeoutMs: 5_000 })
}

export function postJson<T>(
  path: `/${string}`,
  body: object,
  parse: (data: unknown) => T,
  signal?: AbortSignal,
): Promise<T> {
  return requestJson(path, parse, { body, signal, timeoutMs: 35_000 })
}
