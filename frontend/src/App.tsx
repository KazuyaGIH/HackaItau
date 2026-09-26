import { useEffect, useState } from 'react'
import { api } from './api'
import type { HealthResponse } from './types'

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.health().then(setHealth).catch((e: Error) => setError(e.message))
  }, [])

  return (
    <main>
      <h1>Itaú-Native Agent Squads — Crédito Agro (MVP)</h1>
      {error && <div className="banner">Backend indisponível: {error}</div>}
      {health && (
        <div className={`banner ${health.llm_mode === 'real' ? 'real' : ''}`}>
          LLM: <code>{health.llm_mode}</code> · demo_mode: <code>{String(health.demo_mode)}</code>
        </div>
      )}
      <p>Scaffold do kernel (T0). Telas de input, execução, governança, relatório e human gate: S4.</p>
    </main>
  )
}
