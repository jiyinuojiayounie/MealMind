import { getJson } from './apiClient'

type HealthResponse = {
  service: string
  status: 'ok'
}

function parseHealth(data: unknown): HealthResponse {
  if (
    typeof data === 'object' &&
    data !== null &&
    'service' in data &&
    typeof data.service === 'string' &&
    data.service.trim() &&
    'status' in data &&
    data.status === 'ok'
  ) {
    return { service: data.service, status: data.status }
  }

  throw new Error('Invalid health response')
}

export function getHealth(signal: AbortSignal): Promise<HealthResponse> {
  return getJson('/api/v1/health', parseHealth, signal)
}
