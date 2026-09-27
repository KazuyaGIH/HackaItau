import {
  Ban,
  BookOpen,
  ChevronDown,
  ChevronRight,
  CircleCheck,
  CircleX,
  Copy,
  FileText,
  Lock,
  Play,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  Users,
} from 'lucide-react'
import { createElement, useState } from 'react'
import { adjustmentLines, answerLines, highlights, keyFigures } from '../answer'
import { formatElapsed, useNow } from '../hooks'
import { agentIcon } from '../iconMap'
import { REPORT_SECTIONS, usePanel } from '../panel'
import { AGENT_META, CONTEXT_KEY_LABEL, agentName, naturalQuestion, teamsFor } from '../squad'
import type { Notice, Part, Turn } from '../transcript'
import type { AssistReply, CaseState, Report } from '../types'
import { OptionCards } from './Options'
import { SquadActivity } from './SquadActivity'
import { OrchestratorMark } from './ui'

export interface AssistantActions {
  busy: boolean
  onRun: () => void
  onRetry: () => void
  onRegenerate: () => void
  onSuggest: (text: string) => void
}

interface Props extends AssistantActions {
  turn: Extract<Turn, { kind: 'assistant' }>
  state: CaseState | null
  reports: Record<number, Report>
  thinking: string | null
  isNew: (key: string) => boolean
}

export function AssistantMessage({ turn, state, reports, thinking, isNew, ...actions }: Props) {
  const running = turn.parts.some((p) => p.kind === 'activity' && p.block.status === 'running')
  return (
    <div className={`turn assistant${isNew(turn.key) ? ' appear' : ''}`}>
      <OrchestratorMark live={turn.live} />
      <div className="turn-body">
        {turn.parts.map((part) => (
          <div key={part.key} className={isNew(part.key) ? 'appear' : undefined}>
            <PartView part={part} state={state} reports={reports} actions={actions} />
          </div>
        ))}
        {turn.live && !running && thinking && <ThinkingLine text={thinking} />}
      </div>
    </div>
  )
}

// Indicador de que o Orquestrador está pensando fora de uma execução da squad (interpretando, consolidando…).
export function ThinkingLine({ text }: { text: string }) {
  const [start] = useState(() => Date.now())
  const now = useNow(true)
  return (
    <p className="thinking" role="status">
      <span className="shimmer">{text}</span>
      <span className="elapsed">{formatElapsed(now - start)}</span>
    </p>
  )
}

function PartView({
  part,
  state,
  reports,
  actions,
}: {
  part: Part
  state: CaseState | null
  reports: Record<number, Report>
  actions: AssistantActions
}) {
  switch (part.kind) {
    case 'text':
      return (
        <p className={`prose${part.tone === 'ok' ? ' ok' : ''}`}>
          {part.tone === 'ok' && <CircleCheck size={16} />}
          {part.text}
        </p>
      )
    case 'notice':
      return <NoticeView notice={part.notice} />
    case 'plan':
      return (
        <PlanView agents={part.agents} canRun={part.canRun} rerun={part.rerun} busy={actions.busy} onRun={actions.onRun} />
      )
    case 'understanding':
      return state ? <UnderstandingView state={state} /> : null
    case 'question':
      return <QuestionView state={state} active={part.active} />
    case 'ack':
      return (
        <AckView keys={part.keys} source={part.source} canRun={!!part.canRun} busy={actions.busy} onRun={actions.onRun} />
      )
    case 'assist':
      return <AssistView reply={part.reply} onSuggest={actions.onSuggest} busy={actions.busy} />
    case 'activity':
      return (
        <>
          <SquadActivity block={part.block} state={state} />
          {part.block.notices.map((n) => (
            <NoticeView key={n.key} notice={n} />
          ))}
        </>
      )
    case 'answer': {
      const report = reports[part.reportSeq] ?? (part.latest ? state?.report : null) ?? null
      const prevSeq = Math.max(-1, ...Object.keys(reports).map(Number).filter((s) => s < part.reportSeq))
      const previous = part.adjusted && prevSeq >= 0 ? reports[prevSeq] : null
      return <AnswerView part={part} report={report} previous={previous} state={state} actions={actions} />
    }
    case 'error':
      return <ErrorView error={part.error} canRetry={part.canRetry} busy={actions.busy} onRetry={actions.onRetry} />
  }
}

const brlShort = (v: number) =>
  v >= 1e6
    ? `R$ ${(v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} milhões`
    : v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })

// "Entendi o pedido assim": tudo que a leitura da demanda encontrou, o que o analista acrescentou e o que ainda
// mudaria a análise. As perguntas só aparecem enquanto a squad ainda não rodou.
function UnderstandingView({ state }: { state: CaseState }) {
  const it = state.interpreted!
  const facts: Array<[string, string]> = []
  if (it.client_ref) facts.push(['Cliente', it.client_ref + (state.scope ? ` (${state.scope.client_ids.join(', ')})` : '')])
  if (it.requested_amount) facts.push(['Valor', brlShort(it.requested_amount)])
  if (it.purpose) facts.push(['Finalidade', it.purpose])
  if (it.crop || it.cycle) facts.push(['Cultura e safra', [it.crop, it.cycle].filter(Boolean).join(' ')])
  if (it.request_kind) facts.push(['Tipo de operação', it.request_kind.replace(/_/g, ' ')])
  if (it.tenor_months) facts.push(['Prazo desejado', `${it.tenor_months} meses`])
  if (it.guarantees.length) facts.push(['Garantias oferecidas', it.guarantees.join(', ')])
  if (it.region) facts.push(['Região', it.region])
  if (it.area_hectares) facts.push(['Área', `${it.area_hectares.toLocaleString('pt-BR')} ha`])
  const notes = state.analyst_context['Observações']
  const questions = state.status === 'planned' || state.status === 'waiting_input' ? state.open_questions : []
  return (
    <div className="understanding">
      <p className="prose">Entendi o pedido assim:</p>
      <dl className="facts">
        {facts.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      {notes && <p className="small muted">Você acrescentou: {notes.split('\n').join(' / ')}</p>}
      {questions.length > 0 && (
        <>
          <p className="prose">Antes de rodar, alguns pontos ainda mudam a análise:</p>
          <ul className="prose-list">
            {questions.map((q) => (
              <li key={q.key}>{q.question}</li>
            ))}
          </ul>
          <p className="small muted">
            Responda aqui na conversa, anexe documentos, ou execute a squad agora: sem essas respostas ela segue as
            premissas da política.
          </p>
        </>
      )}
    </div>
  )
}

function QuestionView({ state, active }: { state: CaseState | null; active: boolean }) {
  const info = state?.missing_info
  if (!info) return <p className="prose muted">Pedi uma informação complementar, e você respondeu abaixo.</p>
  const { lead, asks } = naturalQuestion(info.reason, info.items)
  return (
    <div className="question">
      <p className="prose">{lead}</p>
      {info.items.some((item) => ['crop', 'planting_plan_crop', 'market_data'].includes(item)) && (
        <p className="prose">{info.message}</p>
      )}
      {asks.length === 1 ? (
        <p className="prose">{asks[0]}</p>
      ) : (
        <ul className="prose-list">
          {asks.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      )}
      {active && <p className="small muted">Responda aqui mesmo, do seu jeito. Nada do que você escrever muda o escopo.</p>}
    </div>
  )
}

const listPt = (items: string[]) =>
  items.length <= 1 ? items.join('') : `${items.slice(0, -1).join(', ')} e ${items[items.length - 1]}`

function AckView({
  keys,
  source,
  canRun,
  busy,
  onRun,
}: {
  keys: string[]
  source: 'text' | 'attachment'
  canRun: boolean
  busy: boolean
  onRun: () => void
}) {
  if (source === 'attachment') {
    return <p className="prose">O documento anexado cumpre o que faltava. Já dá para rodar a squad de novo.</p>
  }
  const labels = keys.filter((k) => k !== 'observacoes_do_analista').map((k) => CONTEXT_KEY_LABEL[k] ?? k.replace(/_/g, ' '))
  return (
    <div className="plan">
      <p className="prose">
        {labels.length ? `Anotei: ${listPt(labels)}.` : 'Anotei a sua observação.'} Isso entra na análise como contexto
        para a squad.
      </p>
      {canRun && (
        <div className="plan-actions">
          <button type="button" className="btn primary" disabled={busy} onClick={onRun}>
            <Play size={15} />
            Executar squad
          </button>
          <span className="muted small">Ou continue acrescentando contexto.</span>
        </div>
      )}
    </div>
  )
}

function AssistView({ reply, onSuggest, busy }: { reply: AssistReply; onSuggest: (t: string) => void; busy: boolean }) {
  const [open, setOpen] = useState<string | null>(null)
  return (
    <div className="assist">
      {reply.message && <p className="prose">{reply.message}</p>}
      {reply.bullets.length > 0 && (
        <ul className="prose-list">
          {reply.bullets.map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
      )}
      {reply.citations.length > 0 && (
        <div className="citations">
          <p className="small muted">Fontes</p>
          {reply.citations.map((c) => (
            <div key={c.id} className="citation">
              <button type="button" onClick={() => setOpen(open === c.id ? null : c.id)} aria-expanded={open === c.id}>
                <BookOpen size={14} />
                <span>{c.title}</span>
                <ChevronDown size={14} className="chev" />
              </button>
              {open === c.id && <p className="citation-text">{c.excerpt}</p>}
            </div>
          ))}
        </div>
      )}
      {reply.suggestions.length > 0 && (
        <div className="suggestion-chips">
          {reply.suggestions.map((s) => (
            <button key={s} type="button" className="pill" disabled={busy} onClick={() => onSuggest(s)}>
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

const NOTICE_ICON = { scope: Lock, denied: Ban, injection: ShieldAlert, guard: ShieldCheck, security: ShieldAlert }

function NoticeView({ notice }: { notice: Notice }) {
  return (
    <div className={`callout ${notice.tone}`}>
      {createElement(NOTICE_ICON[notice.kind], { size: 16 })}
      <p>{notice.text}</p>
    </div>
  )
}

function PlanView({
  agents,
  canRun,
  rerun,
  busy,
  onRun,
}: {
  agents: string[]
  canRun: boolean
  rerun?: boolean
  busy: boolean
  onRun: () => void
}) {
  const teams = teamsFor(agents)
  if (rerun) {
    return (
      <div className="plan">
        <p className="prose">
          Recebi a informação. Ela entra na análise como dado não confiável e não muda o escopo do case.
        </p>
        {canRun && (
          <div className="plan-actions">
            <button type="button" className="btn primary" disabled={busy} onClick={onRun}>
              <Play size={15} />
              Executar squad de novo
            </button>
          </div>
        )}
      </div>
    )
  }
  return (
    <div className="plan">
      <p className="prose">
        Montei uma squad com {agents.length} agentes em {teams.length} {teams.length === 1 ? 'time' : 'times'}. Cada um recebe
        só os dados que a sua tarefa exige.
      </p>
      {canRun &&
        teams.map((team) => (
        <div className="plan-team" key={team.id}>
          <div className="team-head">
            <Users size={15} />
            <span>{team.name}</span>
          </div>
          <ul>
            {team.agents.map((id, i) => (
              <li key={id} style={{ ['--i' as string]: i }}>
                <span className="node">{createElement(agentIcon(id), { size: 15 })}</span>
                <span className="agent-name">{agentName(id)}</span>
                <span className="agent-role">{AGENT_META[id]?.role}</span>
              </li>
            ))}
          </ul>
        </div>
        ))}
      {canRun && (
        <div className="plan-actions">
          <button type="button" className="btn primary" disabled={busy} onClick={onRun}>
            <Play size={15} />
            Executar squad
          </button>
          <span className="muted small">Os dados são coletados por código autorizado; o modelo não chama ferramentas.</span>
        </div>
      )}
    </div>
  )
}

function AnswerView({
  part,
  report,
  previous,
  state,
  actions,
}: {
  part: Extract<Part, { kind: 'answer' }>
  report: Report | null
  previous: Report | null
  state: CaseState | null
  actions: AssistantActions
}) {
  const panel = usePanel()
  const [copied, setCopied] = useState(false)
  if (!report) return <p className="prose muted">Relatório consolidado.</p>
  const lines = previous
    ? [...adjustmentLines(previous, report), ...answerLines(report, { skipRework: true })]
    : answerLines(report)
  const figures = keyFigures(report)
  const notes = highlights(report, previous)
  const lead = part.adjusted
    ? 'Refiz a análise com o seu ajuste. O novo relatório está pronto para a sua revisão.'
    : 'A análise está pronta para a sua revisão. Os números principais:'
  const awaitingDecision = part.latest && state?.status === 'human_review_required'

  const copy = () => {
    const text = [lead, ...lines.map((l) => `- ${l}`)].join('\n')
    navigator.clipboard?.writeText(text).then(
      () => {
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      },
      () => {},
    )
  }

  return (
    <div className="answer">
      <p className="prose">{lead}</p>
      <div className="answer-figures">
        {figures.map((f) => (
          <div key={f.label} className={`figure ${f.tone}`}>
            <span className="figure-label">{f.label}</span>
            <span className="figure-value">{f.value}</span>
            <span className="figure-note">{f.note}</span>
          </div>
        ))}
      </div>
      {notes.length > 0 && (
        <ul className="prose-list">
          {notes.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      )}
      <p className="prose">
        {report.alternatives.length} opções de estrutura para você comparar, sem preferência do sistema:
      </p>
      <OptionCards
        alternatives={report.alternatives}
        compact
        onOpen={() => panel.open({ kind: 'report', reportSeq: part.reportSeq, section: REPORT_SECTIONS.options })}
      />
      <button type="button" className="artifact" onClick={() => panel.open({ kind: 'report', reportSeq: part.reportSeq })}>
        <span className="artifact-icon">
          <FileText size={18} />
        </span>
        <span className="artifact-text">
          <strong>Relatório para revisão humana{part.version > 1 ? `, versão ${part.version}` : ''}</strong>
          <span>
            Capacidade de pagamento, opções, riscos, premissas e fontes ({report.sources.length})
          </span>
        </span>
        <ChevronRight size={18} className="artifact-go" />
      </button>
      <p className="small muted">Análise gerada para suporte à decisão. Não representa aprovação de crédito.</p>
      {awaitingDecision && (
        <p className="prose">A decisão é sua: aprove para a próxima etapa ou descreva um ajuste para a squad.</p>
      )}
      <div className="msg-actions">
        <button type="button" className="icon-btn" onClick={copy} title="Copiar resumo" aria-label="Copiar resumo">
          <Copy size={15} />
          {copied && <span className="copied">Copiado</span>}
        </button>
        {part.latest && (
          <button
            type="button"
            className="icon-btn"
            onClick={actions.onRegenerate}
            disabled={actions.busy}
            title="Rodar a squad de novo, numa nova versão desta conversa"
            aria-label="Gerar de novo"
          >
            <RotateCcw size={15} />
          </button>
        )}
      </div>
    </div>
  )
}

function describeError(error: string): { where: string | null; text: string } {
  const [agent, ...rest] = error.split(':')
  const where = agent in AGENT_META ? agentName(agent) : null
  const detail = where ? rest.join(':').trim() : error
  if (detail.includes('429')) {
    return { where, text: 'O provedor do modelo recusou por limite de requisições (HTTP 429). Espere um minuto e tente de novo.' }
  }
  if (detail.includes('llm_unconfigured')) return { where, text: 'O modelo não está configurado: defina LLM_API_KEY no .env e reinicie o backend.' }
  if (error === 'user_not_authorized_to_resolve_client') {
    return { where: null, text: 'Você não tem permissão para consultar este cliente. Nada foi executado.' }
  }
  return { where, text: detail }
}

function ErrorView({ error, canRetry, busy, onRetry }: { error: string; canRetry: boolean; busy: boolean; onRetry: () => void }) {
  const { where, text } = describeError(error)
  return (
    <div className="callout danger error">
      <CircleX size={16} />
      <div>
        <p>
          <strong>A execução parou{where ? ` em ${where}` : ''}.</strong> {text}
        </p>
        <p className="muted small">O erro ficou registrado na auditoria.</p>
        {canRetry && (
          <button type="button" className="btn secondary" disabled={busy} onClick={onRetry}>
            <RotateCcw size={15} />
            Tentar de novo a partir daqui
          </button>
        )}
      </div>
    </div>
  )
}
