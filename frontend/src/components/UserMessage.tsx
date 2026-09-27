import { ChevronLeft, ChevronRight, CircleCheck, Copy, CornerUpLeft, FileText, Paperclip, Pencil, ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import { DOC_LABEL } from '../squad'
import type { Turn } from '../transcript'
import type { AttachmentView } from '../types'

interface Branching {
  index: number
  count: number
  onSelect: (index: number) => void
  onEdit: (text: string) => void
  disabled: boolean
}

interface Props {
  turn: Extract<Turn, { kind: 'user' }>
  animate: boolean
  branching?: Branching // só na demanda: editar cria uma nova versão da conversa
}

export function UserMessage({ turn, animate, branching }: Props) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(turn.text)

  if (editing && branching) {
    return (
      <div className="turn user editing">
        <div className="edit-box">
          <textarea
            value={draft}
            autoFocus
            rows={3}
            onChange={(e) => setDraft(e.target.value)}
            aria-label="Editar demanda"
          />
          <div className="edit-actions">
            <span className="muted small">Uma nova versão da conversa será criada; a atual continua disponível.</span>
            <button type="button" className="btn secondary" onClick={() => setEditing(false)}>
              Cancelar
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={!draft.trim() || draft.trim() === turn.text.trim()}
              onClick={() => {
                branching.onEdit(draft.trim())
                setEditing(false)
              }}
            >
              Enviar
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (turn.role === 'attachment') {
    return (
      <div className={`turn user attachment${animate ? ' appear' : ''}`}>
        <FileCard name={turn.text} a={turn.attachment} />
      </div>
    )
  }

  const icon =
    turn.role === 'approve' ? <CircleCheck size={15} /> : turn.role === 'adjust' ? <CornerUpLeft size={15} /> : null

  return (
    <div className={`turn user ${turn.role}${animate ? ' appear' : ''}${turn.pending ? ' pending' : ''}`}>
      {turn.detail && (
        <div className="user-detail">
          {icon}
          <span>{turn.detail}</span>
        </div>
      )}
      {turn.attachments?.map((a) => (
        <FileCard key={a.doc_id} name={a.filename} a={a} />
      ))}
      {turn.files && turn.files.length > 0 && (
        <div className="bubble-files">
          {turn.files.map((f) => (
            <span key={f} className="file-chip">
              <Paperclip size={13} />
              {f}
            </span>
          ))}
        </div>
      )}
      {turn.text && <div className="bubble">{turn.text}</div>}
      {(branching || turn.role === 'demand') && !turn.pending && (
        <div className="msg-actions user-actions">
          <button
            type="button"
            className="icon-btn"
            title="Copiar"
            aria-label="Copiar"
            onClick={() => void navigator.clipboard?.writeText(turn.text)}
          >
            <Copy size={15} />
          </button>
          {branching && (
            <button
              type="button"
              className="icon-btn"
              title="Editar demanda"
              aria-label="Editar demanda"
              disabled={branching.disabled}
              onClick={() => {
                setDraft(turn.text)
                setEditing(true)
              }}
            >
              <Pencil size={15} />
            </button>
          )}
          {branching && branching.count > 1 && (
            <span className="branch-nav" aria-label="Versões desta conversa">
              <button
                type="button"
                className="icon-btn"
                aria-label="Versão anterior"
                disabled={branching.index === 0}
                onClick={() => branching.onSelect(branching.index - 1)}
              >
                <ChevronLeft size={15} />
              </button>
              <span className="num">
                {branching.index + 1} / {branching.count}
              </span>
              <button
                type="button"
                className="icon-btn"
                aria-label="Próxima versão"
                disabled={branching.index === branching.count - 1}
                onClick={() => branching.onSelect(branching.index + 1)}
              >
                <ChevronRight size={15} />
              </button>
            </span>
          )}
        </div>
      )}
    </div>
  )
}

// Documento anexado: nome, tipo reconhecido e se o Injection Guard encontrou instruções embutidas.
function FileCard({ name, a }: { name: string; a?: AttachmentView }) {
  return (
    <div className={`file-card${a?.flagged ? ' flagged' : ''}`}>
      <span className="file-icon">
        <FileText size={18} />
      </span>
      <span className="file-text">
        <strong>{name}</strong>
        <span>
          {a ? `${DOC_LABEL[a.doc_type] ?? a.doc_type}, ${a.chars.toLocaleString('pt-BR')} caracteres lidos` : 'anexo'}
          {a?.truncated && ', cortado no limite'}
        </span>
      </span>
      {a?.flagged && (
        <span className="file-flag" title="O documento traz instruções para os agentes; ele é tratado só como dado.">
          <ShieldAlert size={14} />
          instruções suspeitas
        </span>
      )}
    </div>
  )
}
