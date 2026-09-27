import { ArrowDown, ClipboardList, FileText, Lock, PanelLeft, TriangleAlert, X } from 'lucide-react'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { ART } from '../brand'
import { AsciiField } from './AsciiField'
import { seqOfKey } from '../hooks'
import { usePanel } from '../panel'
import { pdfFile } from '../pdf'
import { STARTERS, type Starter } from '../starters'
import { buildTurns, type Turn } from '../transcript'
import type { CaseEvent } from '../types'
import { ACTIVE, type SendOptions, type Workspace } from '../workspace'
import { AssistantMessage } from './AssistantMessage'
import { Composer, type ComposerMode } from './Composer'
import { DecisionBar } from './DecisionBar'
import { UserMessage } from './UserMessage'

interface Props {
  ws: Workspace
  sidebarOpen: boolean
  onOpenSidebar: () => void
}

export function Conversation({ ws, sidebarOpen, onOpenSidebar }: Props) {
  const { current: conv, branch, caseData } = ws
  const panel = usePanel()
  const state = caseData?.state ?? null
  const events = caseData?.events ?? NO_EVENTS
  const status = state?.status
  const active = !!status && ACTIVE.has(status)
  const creating = !!branch?.creating
  const pending = ws.pending
  // a mensagem pendente some quando o evento correspondente chega (ou quando a resposta local entra)
  const pendingShown =
    pending && !events.some((e) => e.seq > pending.sinceSeq && USER_EVENTS.has(e.type)) ? pending : null

  const turns = useMemo(() => {
    const t: Turn[] = buildTurns(state, events, {
      local: branch?.local ?? [],
      inputs: branch?.inputs ?? [],
      active,
    })
    if (pendingShown && (pendingShown.text || pendingShown.files.length)) {
      t.push({
        kind: 'user',
        key: 'pending-user',
        role: 'chat',
        text: pendingShown.text,
        files: pendingShown.files,
        pending: true,
      })
    }
    if (pendingShown || creating) t.push({ kind: 'assistant', key: 'pending-assistant', parts: [], live: true })
    return t
  }, [state, events, branch, active, pendingShown, creating])

  const thinking = creating
    ? 'Lendo a demanda e identificando o cliente'
    : pendingShown
      ? pendingShown.text
        ? 'Lendo a sua mensagem'
        : 'Lendo o documento'
      : status === 'interpreting'
        ? 'Lendo a demanda e identificando o cliente'
        : status === 'consolidating'
          ? 'Consolidando o relatório'
          : active
            ? 'Coordenando a squad'
            : null

  // Anima só o que chegou depois que a conversa foi aberta (o histórico aparece parado).
  const branchKey = branch?.id ?? 'none'
  const loadedSeq = caseData ? caseData.lastSeq : branch && !branch.caseId ? 0 : null
  const [baseline, setBaseline] = useState<{ id: string; seq: number | null }>({ id: '', seq: null })
  if (baseline.id !== branchKey || (baseline.seq === null && loadedSeq !== null)) {
    setBaseline({ id: branchKey, seq: loadedSeq })
  }
  const isNew = (key: string) => {
    if (key.startsWith('pending')) return true
    if (baseline.seq === null) return false
    const s = seqOfKey(key)
    return s === null ? true : s > baseline.seq
  }

  // Rolagem: acompanha o fim enquanto o usuário estiver no fim; senão mostra o botão de voltar ao fim.
  const scroller = useRef<HTMLDivElement>(null)
  const [atBottom, setAtBottom] = useState(true)
  const signature = `${branchKey}|${caseData?.lastSeq ?? 0}|${turns.length}|${thinking ?? ''}|${status ?? ''}`
  useLayoutEffect(() => {
    const el = scroller.current
    if (el && atBottom) el.scrollTop = el.scrollHeight
  }, [signature, atBottom])
  // trocar de conversa volta para o fim
  const [scrolledBranch, setScrolledBranch] = useState(branchKey)
  if (scrolledBranch !== branchKey) {
    setScrolledBranch(branchKey)
    setAtBottom(true)
  }

  const send = (text: string, opts: SendOptions) => void ws.send(text, opts)
  const suggest = (text: string) => send(text, { target: '', files: [] })
  const start = (s: Starter) => send(s.prompt, { target: '', files: s.file ? [pdfFile(s.file.name, s.file.lines)] : [] })

  const mode: ComposerMode = !branch
    ? 'new'
    : caseData?.missing
      ? 'locked'
      : creating || active || pendingShown
        ? 'working'
        : !branch.caseId
          ? 'new'
          : status === 'human_review_required'
            ? 'adjust'
            : status === 'waiting_input' || status === 'planned'
              ? 'reply'
              : 'chat'
  const placeholder = {
    new: 'Descreva a operação ou faça uma pergunta sobre crédito agro',
    chat: 'Pergunte sobre a análise, as políticas ou os documentos',
    reply:
      status === 'waiting_input'
        ? 'Responda aqui ou anexe o documento'
        : 'Acrescente contexto (prazo, garantias, observações) ou execute a squad',
    adjust: 'Peça um ajuste ou pergunte sobre a análise',
    working: 'A squad está trabalhando',
    locked: 'Este case não existe mais no servidor',
  }[mode]

  if (!conv || !branch) {
    return (
      <main className="main">
        <TopBar sidebarOpen={sidebarOpen} onOpenSidebar={onOpenSidebar} />
        <AsciiField className="empty-field" />
        <div className="empty">
          <img className="empty-art" src={ART} alt="" />
          <h1>Qual demanda de crédito vamos analisar?</h1>
          <p className="muted">
            O Orquestrador monta uma squad de agentes especialistas, cada um com acesso só ao que a tarefa exige. A decisão
            final é sempre sua.
          </p>
          <Composer mode="new" placeholder={placeholder} onSend={send} autoFocus />
          <div className="suggestions">
            {STARTERS.map((s, i) => (
              <button key={s.label} type="button" onClick={() => start(s)}>
                <span className="sugg-num">{String(i + 1).padStart(3, '0')}</span>
                <span>
                  <strong>{s.label}</strong>
                  <span className="muted">{s.hint}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      </main>
    )
  }

  const report = state?.report
  const branching = {
    index: conv.active,
    count: conv.branches.length,
    onSelect: (i: number) => ws.selectBranch(conv.id, i),
    onEdit: (text: string) => ws.branchFrom(conv, text, 'edit'),
    disabled: creating || active,
  }

  return (
    <main className="main">
      <TopBar
        sidebarOpen={sidebarOpen}
        onOpenSidebar={onOpenSidebar}
        title={ws.titleOf(conv)}
        scope={state?.scope?.client_ids.join(', ')}
        onReport={report ? () => panel.open({ kind: 'report', reportSeq: null }) : undefined}
        onAudit={state ? () => panel.open({ kind: 'audit' }) : undefined}
      />
      <div className="scroller" ref={scroller} onScroll={(e) => {
        const el = e.currentTarget
        setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80)
      }}>
        <div className="thread">
          {turns.map((t) =>
            t.kind === 'user' ? (
              <UserMessage
                key={t.key}
                turn={t}
                animate={isNew(t.key) && t.role !== 'demand'}
                branching={t.role === 'demand' ? branching : undefined}
              />
            ) : (
              <AssistantMessage
                key={t.key}
                turn={t}
                state={state}
                reports={caseData?.reports ?? {}}
                thinking={thinking}
                isNew={isNew}
                busy={active || !!pendingShown}
                onRun={() => state && void ws.run(state.case_id)}
                onRetry={() => state && void ws.retry(state.case_id)}
                onRegenerate={() => ws.branchFrom(conv, branch.prompt, 'regenerate')}
                onSuggest={suggest}
              />
            ),
          )}
          {branch.error && (
            <div className="callout danger">
              <TriangleAlert size={16} />
              <div>
                <p>Não consegui abrir o case: {branch.error}</p>
                <button type="button" className="btn secondary" onClick={() => ws.restartBranch(conv.id, branch)}>
                  Tentar de novo
                </button>
              </div>
            </div>
          )}
          {caseData?.missing && (
            <div className="callout warn">
              <TriangleAlert size={16} />
              <p>O servidor foi reiniciado e este case não existe mais (o estado fica em memória). Comece uma nova conversa.</p>
            </div>
          )}
        </div>
      </div>
      <div className="dock">
        {!atBottom && (
          <button
            type="button"
            className="to-bottom"
            aria-label="Ir para a mensagem mais recente"
            onClick={() => {
              scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' })
            }}
          >
            <ArrowDown size={16} />
          </button>
        )}
        {ws.error && (
          <div className="callout danger toast" role="alert">
            <TriangleAlert size={16} />
            <p>{ws.error}</p>
            <button type="button" className="icon-btn" aria-label="Fechar aviso" onClick={() => ws.setError(null)}>
              <X size={15} />
            </button>
          </div>
        )}
        {status === 'human_review_required' && !pendingShown && (
          <DecisionBar
            userId={state?.user_id ?? ws.userId}
            busy={!!pendingShown}
            onApprove={(comment) => void ws.humanReview(branch, { decision: 'approve_next_step', comment })}
          />
        )}
        <Composer key={branch.id} mode={mode} placeholder={placeholder} onSend={send} />
        <p className="dock-note">Ambiente de demonstração com dados fictícios. A squad prepara a análise; quem decide é você.</p>
      </div>
    </main>
  )
}

const NO_EVENTS: CaseEvent[] = []

const USER_EVENTS: ReadonlySet<string> = new Set([
  'CASE_CREATED',
  'HUMAN_ADJUSTMENT_REQUESTED',
  'HUMAN_APPROVED',
  'INPUT_RECEIVED',
  'DOCUMENT_ATTACHED',
])

interface TopBarProps {
  sidebarOpen: boolean
  onOpenSidebar: () => void
  title?: string
  scope?: string
  onReport?: () => void
  onAudit?: () => void
}

function TopBar({ sidebarOpen, onOpenSidebar, title, scope, onReport, onAudit }: TopBarProps) {
  return (
    <header className="topbar">
      {!sidebarOpen && (
        <button type="button" className="icon-btn" onClick={onOpenSidebar} aria-label="Abrir barra lateral" title="Abrir barra lateral">
          <PanelLeft size={18} />
        </button>
      )}
      <p className="topbar-title">{title ?? 'Nova conversa'}</p>
      {scope && (
        <span className="scope-pill" title="Escopo travado: nenhum agente acessa outro cliente">
          <Lock size={13} />
          {scope}
        </span>
      )}
      <div className="topbar-actions">
        {onReport && (
          <button type="button" className="icon-btn with-label" onClick={onReport}>
            <FileText size={16} />
            <span>Relatório</span>
          </button>
        )}
        {onAudit && (
          <button type="button" className="icon-btn with-label" onClick={onAudit}>
            <ClipboardList size={16} />
            <span>Auditoria</span>
          </button>
        )}
      </div>
    </header>
  )
}
