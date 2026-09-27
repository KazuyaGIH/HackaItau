import { CircleAlert, CircleCheck, CircleDot, FlaskConical, LoaderCircle, PanelLeft, SquarePen, User } from 'lucide-react'
import type { CaseStatus } from '../types'
import { ACTIVE, USER_ID, type Conversation } from '../workspace'
import { OrchestratorMark } from './ui'

interface Props {
  conversations: Conversation[]
  currentId: string | null
  statusOf: (c: Conversation) => CaseStatus | 'creating' | 'error' | null
  titleOf: (c: Conversation) => string
  onOpen: (id: string) => void
  onNew: () => void
  onClose: () => void
  llmReady: boolean | null
}

function StatusIcon({ status }: { status: CaseStatus | 'creating' | 'error' | null }) {
  if (status === 'creating' || (status && ACTIVE.has(status as CaseStatus))) {
    return <LoaderCircle size={14} className="spin" aria-label="squad trabalhando" />
  }
  if (status === 'human_review_required' || status === 'waiting_input' || status === 'planned') {
    return <CircleDot size={14} className="waiting" aria-label="aguardando você" />
  }
  if (status === 'completed_demo') return <CircleCheck size={14} className="done" aria-label="concluída" />
  if (status === 'failed' || status === 'error') return <CircleAlert size={14} className="failed" aria-label="com erro" />
  return null
}

export function Sidebar({ conversations, currentId, statusOf, titleOf, onOpen, onNew, onClose, llmReady }: Props) {
  return (
    <nav className="sidebar" aria-label="Conversas">
      <div className="sidebar-top">
        <div className="brand">
          <OrchestratorMark size={26} />
          <span>Agent Squads</span>
        </div>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Fechar barra lateral" title="Fechar barra lateral">
          <PanelLeft size={18} />
        </button>
      </div>

      <button type="button" className="new-chat" onClick={onNew}>
        <SquarePen size={17} />
        Nova conversa
      </button>

      <div className="conv-list">
        {conversations.length > 0 && <p className="conv-label">Conversas</p>}
        {conversations.map((c) => {
          const status = statusOf(c)
          return (
            <button
              key={c.id}
              type="button"
              className={`conv${c.id === currentId ? ' current' : ''}`}
              onClick={() => onOpen(c.id)}
              title={titleOf(c)}
            >
              <span className="conv-title">{titleOf(c)}</span>
              {c.branches.length > 1 && <span className="conv-versions">{c.branches.length} versões</span>}
              <StatusIcon status={status} />
            </button>
          )
        })}
      </div>

      <div className="sidebar-foot">
        <div className="who">
          <span className="avatar">
            <User size={16} />
          </span>
          <span>
            <strong>{USER_ID}</strong>
            <span className="muted small">Analista de crédito</span>
          </span>
        </div>
        <p className="env">
          <FlaskConical size={14} />
          Ambiente de demonstração com dados fictícios.
        </p>
        {llmReady === false && (
          <p className="env warn">
            <CircleAlert size={14} />
            Modelo não configurado: defina LLM_API_KEY no .env.
          </p>
        )}
      </div>
    </nav>
  )
}
