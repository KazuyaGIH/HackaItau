import { useState } from 'react'
import type { CaseState, HumanReviewRequest } from '../types'

interface Props {
  state: CaseState
  busy: boolean
  onDecide: (body: HumanReviewRequest) => void
}

export function HumanGate({ state, busy, onDecide }: Props) {
  const [comment, setComment] = useState('')
  const gate = state.report?.human_gate
  if (!gate) return null
  const done = state.status === 'completed_demo'

  return (
    <section className="card gate">
      <h2>4. Decisão humana</h2>
      <p>
        {gate.notice} O sistema <b>não aprova nem rejeita crédito</b>: ele organiza evidências, cálculos, riscos e
        alternativas para que a decisão seja tomada por uma pessoa.
      </p>
      {gate.comments.length > 0 && (
        <ul className="items">
          {gate.comments.map((c, i) => (
            <li key={i}>
              <span className="tag">comentário</span> {c}
            </li>
          ))}
        </ul>
      )}
      {done ? (
        <div className="banner ok">
          <b>Etapa concluída (demo).</b> Aprovação registrada para a <i>próxima etapa do processo</i> — não é aprovação de
          crédito. Estado final: <code>{state.status}</code>.
        </div>
      ) : (
        <>
          {gate.status === 'adjustment_requested' && (
            <div className="banner warn">
              Ajuste solicitado e registrado na auditoria. No MVP a reexecução automática não está habilitada (P1).
            </div>
          )}
          <textarea
            rows={2}
            placeholder="Comentário do analista (opcional)"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <div className="row">
            {gate.available_actions.includes('request_adjustment') && (
              <button
                className="secondary"
                disabled={busy}
                onClick={() => onDecide({ decision: 'request_adjustment', comment })}
              >
                Solicitar ajuste
              </button>
            )}
            {gate.available_actions.includes('approve_next_step') && (
              <button disabled={busy} onClick={() => onDecide({ decision: 'approve_next_step', comment })}>
                Aprovar para próxima etapa
              </button>
            )}
          </div>
        </>
      )}
    </section>
  )
}
