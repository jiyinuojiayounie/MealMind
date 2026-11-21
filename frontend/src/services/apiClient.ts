const baseUrl = (
  import.meta.env.VITE_API_BASE_URL?.trim() ||
  (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '')
).replace(/\/+$/, '')

export class ApiError extends Error {
  readonly status: number

  constructor(status: number) {
    super(`API request failed with HTTP ${status}`)
    this.status = status
  }
}

type JsonRequest = {
  body?: object
  signal?: AbortSignal
  timeoutMs: number
}

async function requestJson<T>(
  path: `/${string}`,
  parse: (data: unknown) => T,
  { body, signal, timeoutMs }: JsonRequest,
): Promise<T> {
  const timeout = AbortSignal.timeout(timeoutMs)
  const response = await fetch(`${baseUrl}${path}`, {
    method: body ? 'POST' : 'GET',
    headers: body
      ? { Accept: 'application/json', 'Content-Type': 'application/json' }
      : { Accept: 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'omit',
    cache: 'no-store',
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  })

  if (!response.ok) throw new ApiError(response.status)
  return parse(await response.json())
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
