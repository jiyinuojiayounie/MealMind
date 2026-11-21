const baseUrl = (
  import.meta.env.VITE_API_BASE_URL?.trim() ||
  (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '')
).replace(/\/+$/, '')

export async function getJson<T>(
  path: `/${string}`,
  parse: (data: unknown) => T,
  signal?: AbortSignal,
): Promise<T> {
  const timeout = AbortSignal.timeout(5_000)
  const response = await fetch(`${baseUrl}${path}`, {
    headers: { Accept: 'application/json' },
    credentials: 'omit',
    cache: 'no-store',
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  })

  if (!response.ok) {
    throw new Error(`API request failed with HTTP ${response.status}`)
  }

  return parse(await response.json())
}
