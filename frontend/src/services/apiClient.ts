export const apiBaseUrl = (
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

export async function requestJson<T>(
  path: `/${string}`,
  parse: (data: unknown) => T,
  { body, method = body ? 'POST' : 'GET', redirect, signal, timeoutMs }: JsonRequest,
): Promise<T> {
  const timeout = AbortSignal.timeout(timeoutMs)
  const multipart = body instanceof FormData
  const response = await fetch(`${apiBaseUrl}${path}`, {
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
