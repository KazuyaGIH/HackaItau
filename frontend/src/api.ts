import type { HealthResponse } from './types'

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return (await res.json()) as T
}

export const api = {
  health: () => fetch('/api/health').then(json<HealthResponse>),
}
