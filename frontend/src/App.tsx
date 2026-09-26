import { useEffect, useState } from 'react'
import { api } from './api'
import { CaseInput } from './components/CaseInput'
import { HumanGate } from './components/HumanGate'
import { ReportView } from './components/ReportView'
import { SquadBoard } from './components/SquadBoard'
import { STATUS_LABEL } from './format'
import type { HealthResponse } from './types'
import { useCase } from './useCase'

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)
  const c = useCase()

  useEffect(() => {
    api.health().then(setHealth).catch((e: Error) => setHealthError(e.message))
  }, [])

  return (
    <main>
      <header className="top">
        <div>
          <h1>Itaú-Native Agent Squads — Crédito Agro</h1>
          <p className="muted small">
            LLM propõe · backend autoriza · tool executa · audit registra · <b>humano decide</b>
          </p>
        </div>
        <div className="badges">
          <span className="tag warn">dados fictícios (demo)</span>
          {healthError && <span className="tag danger">backend indisponível: {healthError}</span>}
          {health && (
            <span className={`tag ${health.llm_mode === 'real' ? 'ok' : 'warn'}`}>LLM: {health.llm_mode}</span>
          )}
          {c.state && (
            <span className={`tag status-${c.state.status}`}>
              {STATUS_LABEL[c.state.status]}
              {c.active && <span className="spinner" />}
            </span>
          )}
        </div>
      </header>

      {c.error && <div className="banner danger">{c.error}</div>}

      {!c.state ? (
        <CaseInput disabled={c.busy} onSubmit={c.create} />
      ) : (
        <section className="card compact">
          <div className="row between">
            <div>
              <span className="muted small">case {c.state.case_id}</span>
              <p className="prompt">“{c.state.prompt}”</p>
              {c.state.demo_options.adversarial_document && <span className="tag danger">documento adversarial incluído</span>}
              {c.state.interpreted && (
                <p className="muted small">
                  interpretado: cliente <b>{c.state.interpreted.client_ref ?? '?'}</b> · valor{' '}
                  {c.state.interpreted.requested_amount?.toLocaleString('pt-BR') ?? '?'} · {c.state.interpreted.purpose ?? '?'} ·{' '}
                  {c.state.interpreted.crop ?? '?'} {c.state.interpreted.cycle ?? ''}
                </p>
              )}
            </div>
            <button className="ghost" onClick={c.reset} disabled={c.busy || c.active}>
              novo case
            </button>
          </div>
        </section>
      )}

      {c.state && (
        <SquadBoard
          state={c.state}
          events={c.events}
          busy={c.busy}
          onRun={() => void c.run()}
          onInput={(answers) => void c.provideInput(answers)}
        />
      )}
      {c.state?.report && <ReportView caseId={c.state.case_id} report={c.state.report} />}
      {c.state?.report && <HumanGate state={c.state} busy={c.busy} onDecide={(b) => void c.humanReview(b)} />}
    </main>
  )
}
