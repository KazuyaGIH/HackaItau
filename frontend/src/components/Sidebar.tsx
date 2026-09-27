import {
  ChartColumn,
  CircleAlert,
  CircleCheck,
  CircleDot,
  FlaskConical,
  LoaderCircle,
  PanelLeft,
  SquarePen,
  Trash2,
  User,
} from 'lucide-react'
import { useState } from 'react'
import type { CaseStatus } from '../types'
import { ACTIVE, USER_ID, type Conversation } from '../workspace'
import { OrchestratorMark } from './ui'

interface Props {
  conversations: Conversation[]
  currentId: string | null
  statusOf: (c: Conversation) => CaseStatus | 'creating' | 'error' | null
  titleOf: (c: Conversation) => string
  onOpen: (id: string) => void
  onDelete: (id: string) => void
  onNew: () => void
  onClose: () => void
  onPerformance: () => void
  performanceActive: boolean
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

function ConversationRow({
  conv,
  title,
  status,
  current,
  onOpen,
  onDelete,
}: {
  conv: Conversation
  title: string
  status: CaseStatus | 'creating' | 'error' | null
  current: boolean
  onOpen: () => void
  onDelete: () => void
}) {
  const [confirming, setConfirming] = useState(false)
  if (confirming) {
    return (
      <div className="conv confirm" role="group" aria-label="Confirmar exclusão">
        <span className="conv-title">Apagar?</span>
        <button type="button" className="conv-danger" onClick={onDelete}>
          Apagar
        </button>
        <button type="button" className="conv-cancel" onClick={() => setConfirming(false)} autoFocus>
          Cancelar
        </button>
      </div>
    )
  }
  return (
    <div className={`conv${current ? ' current' : ''}`}>
      <button type="button" className="conv-open" onClick={onOpen} title={title}>
        <span className="conv-title">{title}</span>
        {conv.branches.length > 1 && <span className="conv-versions">{conv.branches.length} versões</span>}
        <StatusIcon status={status} />
      </button>
      <button
        type="button"
        className="conv-delete"
        aria-label={`Apagar conversa: ${title}`}
        title="Apagar conversa"
        onClick={() => setConfirming(true)}
      >
        <Trash2 size={14} />
      </button>
    </div>
  )
}

export function Sidebar({
  conversations,
  currentId,
  statusOf,
  titleOf,
  onOpen,
  onDelete,
  onNew,
  onClose,
  onPerformance,
  performanceActive,
  llmReady,
}: Props) {
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
      <button type="button" className={`new-chat${performanceActive ? ' current' : ''}`} onClick={onPerformance}>
        <ChartColumn size={17} />
        Desempenho dos agentes
      </button>

      <div className="conv-list">
        {conversations.length > 0 && <p className="conv-label">Conversas</p>}
        {conversations.map((c) => (
          <ConversationRow
            key={c.id}
            conv={c}
            title={titleOf(c)}
            status={statusOf(c)}
            current={c.id === currentId && !performanceActive}
            onOpen={() => onOpen(c.id)}
            onDelete={() => onDelete(c.id)}
          />
        ))}
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
