import { CircleCheck, Scale } from 'lucide-react'
import { useState } from 'react'

interface Props {
  userId: string
  busy: boolean
  onApprove: (comment: string) => void
}

// Gate humano: aprovar é uma ação explícita, com confirmação. Ajustes vão pelo campo de mensagem.
export function DecisionBar({ userId, busy, onApprove }: Props) {
  const [confirming, setConfirming] = useState(false)
  const [comment, setComment] = useState('')

  if (confirming) {
    return (
      <div className="decision confirming" role="group" aria-label="Confirmar aprovação">
        <Scale size={18} />
        <div className="decision-text">
          <p>
            <strong>Aprovar para a próxima etapa?</strong> Isto não aprova crédito: registra na auditoria que você, {userId},
            revisou a análise da squad.
          </p>
          <input
            value={comment}
            autoFocus
            placeholder="Comentário para a auditoria (opcional)"
            onChange={(e) => setComment(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onApprove(comment)
              if (e.key === 'Escape') setConfirming(false)
            }}
          />
        </div>
        <div className="decision-actions">
          <button type="button" className="btn secondary" onClick={() => setConfirming(false)} disabled={busy}>
            Voltar
          </button>
          <button type="button" className="btn primary" onClick={() => onApprove(comment)} disabled={busy}>
            Confirmar aprovação
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="decision" role="group" aria-label="Decisão humana">
      <Scale size={18} />
      <p className="decision-text">
        <strong>A decisão é sua.</strong> Aprove a análise ou descreva abaixo um ajuste para a squad.
      </p>
      <button type="button" className="btn primary" onClick={() => setConfirming(true)} disabled={busy}>
        <CircleCheck size={15} />
        Aprovar para a próxima etapa
      </button>
    </div>
  )
}
