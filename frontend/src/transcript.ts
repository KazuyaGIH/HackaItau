// Constrói a conversa a partir do Event Log do case. Função pura: mesmo (state, events, local) → mesma conversa.
// O Orquestrador é a única voz. Cada execução da squad vira um bloco de atividade dentro da resposta dele.
import { SECURITY_LABEL, agentName, deniedTarget, denyReason, stepOf, type Step, type Tone } from './squad'
import type { CaseEvent, CaseState } from './types'

export type NoticeKind = 'scope' | 'denied' | 'injection' | 'guard' | 'security'

export interface Notice {
  key: string
  kind: NoticeKind
  text: string
  tone: Tone
}

export type AgentRunStatus = 'queued' | 'running' | 'done' | 'reopened' | 'failed' | 'blocked'

export interface AgentRun {
  agentId: string
  status: AgentRunStatus
  round: number
  steps: Step[]
  lastEvent: CaseEvent | null
  outputIds: string[]
  reopenedBy: 'review' | 'human' | null
  toolCalls: number
}

export interface ReviewRound {
  round: number
  status: string
  findingIds: string[]
  reopen: string | null
}

export type BlockPhase = 'execution' | 'human_adjustment' | 'retry'

export interface ActivityBlock {
  key: string
  phase: BlockPhase
  startTs: string
  endTs: string | null
  status: 'running' | 'done' | 'failed' | 'blocked'
  order: string[]
  agents: Record<string, AgentRun>
  reviews: ReviewRound[]
  toolCalls: number
  denied: number
  security: number
  notices: Notice[]
  targetAgent: string | null
  failedAgent: string | null
}

export type Part =
  | { kind: 'text'; key: string; text: string; tone?: Tone }
  | { kind: 'notice'; key: string; notice: Notice }
  | { kind: 'plan'; key: string; agents: string[]; canRun: boolean }
  | { kind: 'missing_info'; key: string; active: boolean }
  | { kind: 'activity'; key: string; block: ActivityBlock }
  | { kind: 'answer'; key: string; reportSeq: number; version: number; adjusted: boolean; latest: boolean }
  | { kind: 'error'; key: string; error: string; canRetry: boolean }

export type UserRole = 'demand' | 'input' | 'adjust' | 'note' | 'approve' | 'chat'

export type Turn =
  | { kind: 'user'; key: string; role: UserRole; text: string; detail?: string; pending?: boolean }
  | { kind: 'assistant'; key: string; parts: Part[]; live: boolean }

// Turnos que nascem no cliente (texto livre respondido localmente), ancorados ao último seq visto.
export interface LocalMessage {
  afterSeq: number
  turn: Turn
}

interface BuildOptions {
  local: LocalMessage[]
  inputs: string[]
  active: boolean
}

export function buildTurns(state: CaseState | null, events: CaseEvent[], opts: BuildOptions): Turn[] {
  const turns: Turn[] = []
  let cur: Extract<Turn, { kind: 'assistant' }> | null = null
  let block: ActivityBlock | null = null
  let lastBlock: ActivityBlock | null = null
  let reviewFindings: string[] = []
  let consolidations = 0
  let inputIdx = 0
  let adjustedPending = false
  const gateComments = [...(state?.report?.human_gate.comments ?? [])]
  const locals = [...opts.local].sort((a, b) => a.afterSeq - b.afterSeq)

  const assistant = (key: string) => {
    if (!cur) {
      cur = { kind: 'assistant', key: `a-${key}`, parts: [], live: false }
      turns.push(cur)
    }
    return cur
  }
  const user = (t: Extract<Turn, { kind: 'user' }>) => {
    turns.push(t)
    cur = null
  }
  const flushLocals = (upTo: number) => {
    while (locals.length && locals[0].afterSeq < upTo) {
      turns.push(locals.shift()!.turn)
      cur = null
    }
  }

  for (const e of events) {
    flushLocals(e.seq)
    const p = e.payload
    const k = `e${e.seq}`

    // eventos de agente dentro de uma execução alimentam o bloco da squad
    if (block && e.agent_id && AGENT_EVENTS.has(e.type)) {
      applyAgentEvent(block, e)
      if (e.type === 'REVIEW_ISSUE_FOUND') reviewFindings.push(String(p.finding_id))
      if (e.type !== 'EXECUTION_FAILED') continue
    }

    switch (e.type) {
      case 'CASE_CREATED':
        if (state) user({ kind: 'user', key: k, role: 'demand', text: state.prompt })
        break
      case 'SCOPE_FROZEN': {
        const a = assistant(k)
        const it = state?.interpreted
        if (it) a.parts.push({ kind: 'text', key: `${k}-i`, text: understood(it) })
        a.parts.push({
          kind: 'notice',
          key: k,
          notice: {
            key: k,
            kind: 'scope',
            tone: 'neutral',
            text: `Escopo travado em ${(p.client_ids as string[]).join(', ')}. Nenhum agente pode acessar outro cliente neste case.`,
          },
        })
        break
      }
      case 'AGENT_SELECTED': {
        const a = assistant(k)
        if (!a.parts.some((x) => x.kind === 'plan')) {
          a.parts.push({ kind: 'plan', key: k, agents: state?.selected_agents ?? [], canRun: false })
        }
        break
      }
      case 'MISSING_INFO_REQUESTED': {
        if (block) {
          block.status = 'blocked'
          block.endTs = e.ts
          block = null
        }
        const isLast = !events.some((x) => x.seq > e.seq && x.type === 'MISSING_INFO_REQUESTED')
        assistant(k).parts.push({ kind: 'missing_info', key: k, active: isLast && state?.status === 'waiting_input' })
        break
      }
      case 'INPUT_RECEIVED': {
        const text = opts.inputs[inputIdx] ?? `Informação enviada (${((p.keys as string[]) ?? []).join(', ')})`
        inputIdx += 1
        user({ kind: 'user', key: k, role: 'input', text })
        break
      }
      case 'ORCHESTRATOR_STARTED': {
        if (p.phase === 'bootstrap') break
        const phase = p.phase as BlockPhase
        const a = assistant(k)
        if (phase === 'retry') {
          const from = p.failed_agent ? ` a partir de ${agentName(String(p.failed_agent))}` : ''
          a.parts.push({
            kind: 'text',
            key: `${k}-t`,
            text: `Retomando${from}. O que já tinha concluído não roda de novo.`,
          })
        }
        const order = (p.plan as string[] | undefined) ?? lastBlock?.order ?? []
        block = newBlock(e, phase, [...order], phase === 'retry' ? lastBlock : null)
        if (phase === 'human_adjustment') block.targetAgent = String(p.target_agent)
        lastBlock = block
        reviewFindings = []
        a.parts.push({ kind: 'activity', key: k, block })
        break
      }
      case 'REVIEW_COMPLETED':
        if (block) {
          block.reviews.push({
            round: Number(p.round),
            status: String(p.review_status),
            findingIds: reviewFindings,
            reopen: p.reexecution_required ? String(p.reopen_agent) : null,
          })
          reviewFindings = []
        }
        break
      case 'SECURITY_EVENT':
        if (!e.agent_id) {
          assistant(k).parts.push({
            kind: 'notice',
            key: k,
            notice: { key: k, kind: 'security', tone: 'danger', text: SECURITY_LABEL[String(p.kind)] ?? String(p.kind) },
          })
        }
        break
      case 'RESULT_CONSOLIDATED': {
        if (block) {
          block.status = 'done'
          block.endTs = e.ts
          block = null
        }
        consolidations += 1
        assistant(k).parts.push({
          kind: 'answer',
          key: k,
          reportSeq: e.seq,
          version: consolidations,
          adjusted: adjustedPending,
          latest: false,
        })
        adjustedPending = false
        break
      }
      case 'OUTPUT_GUARD_APPLIED':
        assistant(k).parts.push({
          kind: 'notice',
          key: k,
          notice: {
            key: k,
            kind: 'guard',
            tone: 'warn',
            text: `O filtro de saída revisou o relatório antes de exibi-lo: ${String(p.redactions ?? 0)} trecho(s) removido(s) ou movido(s) para incertezas.`,
          },
        })
        break
      case 'HUMAN_ADJUSTMENT_REQUESTED': {
        const comment = Number(p.comment_len) > 0 ? (gateComments.shift() ?? '') : ''
        const target = p.target_agent ? String(p.target_agent) : null
        user({
          kind: 'user',
          key: k,
          role: target ? 'adjust' : 'note',
          text: comment,
          detail: target ? `Ajuste para ${agentName(target)}` : 'Comentário',
        })
        if (target) adjustedPending = true
        else assistant(k).parts.push({ kind: 'text', key: `${k}-r`, text: 'Registrei o comentário no relatório.' })
        break
      }
      case 'HUMAN_APPROVED': {
        const comment = Number(p.comment_len) > 0 ? (gateComments.shift() ?? '') : ''
        user({ kind: 'user', key: k, role: 'approve', text: comment, detail: 'Aprovado para a próxima etapa' })
        break
      }
      case 'CASE_COMPLETED':
        assistant(k).parts.push({
          kind: 'text',
          key: k,
          tone: 'ok',
          text: 'Aprovação registrada na auditoria. O case segue para a próxima etapa do processo; isto não é uma aprovação de crédito.',
        })
        break
      case 'EXECUTION_FAILED': {
        if (block) {
          block.status = 'failed'
          block.failedAgent = e.agent_id
          block.endTs = e.ts
          block = null
        }
        assistant(k).parts.push({ kind: 'error', key: k, error: String(p.error), canRetry: false })
        break
      }
    }
  }
  flushLocals(Number.POSITIVE_INFINITY)

  // Estado atual: o plano só pode ser executado se o case estiver planejado; retry só na última falha.
  const parts = turns.flatMap((t) => (t.kind === 'assistant' ? t.parts : []))
  const plan = findLast(parts, 'plan')
  if (plan) plan.canRun = state?.status === 'planned' && !parts.some((x) => x.kind === 'activity')
  const err = findLast(parts, 'error')
  if (err && state?.status === 'failed') err.canRetry = lastBlock !== null
  const answer = findLast(parts, 'answer')
  if (answer) answer.latest = true
  const last = turns[turns.length - 1]
  if (last?.kind === 'assistant') last.live = opts.active
  return turns
}

function findLast<K extends Part['kind']>(parts: Part[], kind: K): Extract<Part, { kind: K }> | undefined {
  for (let i = parts.length - 1; i >= 0; i--) {
    if (parts[i].kind === kind) return parts[i] as Extract<Part, { kind: K }>
  }
  return undefined
}

const AGENT_EVENTS: ReadonlySet<string> = new Set([
  'AGENT_STARTED',
  'TOOL_CALLED',
  'PERMISSION_DENIED',
  'SECURITY_EVENT',
  'LLM_CALLED',
  'OUTPUT_REJECTED',
  'GROUNDING_REJECTED',
  'AGENT_COMPLETED',
  'TASK_REOPENED',
  'REVIEW_ISSUE_FOUND',
  'EXECUTION_FAILED',
])

const emptyRun = (agentId: string): AgentRun => ({
  agentId,
  status: 'queued',
  round: 1,
  steps: [],
  lastEvent: null,
  outputIds: [],
  reopenedBy: null,
  toolCalls: 0,
})

// Um retry herda o estado do bloco que falhou: quem já concluiu aparece concluído, o resto volta para a fila.
function newBlock(e: CaseEvent, phase: BlockPhase, order: string[], inherit: ActivityBlock | null): ActivityBlock {
  const agents: Record<string, AgentRun> = {}
  for (const id of order) {
    const prev = inherit?.agents[id]
    agents[id] = prev
      ? { ...prev, steps: [...prev.steps], outputIds: [...prev.outputIds], status: prev.status === 'done' ? 'done' : 'queued' }
      : emptyRun(id)
  }
  return {
    key: `b${e.seq}`,
    phase,
    startTs: e.ts,
    endTs: null,
    status: 'running',
    order,
    agents,
    reviews: inherit ? [...inherit.reviews] : [],
    toolCalls: inherit?.toolCalls ?? 0,
    denied: inherit?.denied ?? 0,
    security: inherit?.security ?? 0,
    notices: inherit ? [...inherit.notices] : [],
    targetAgent: inherit?.targetAgent ?? null,
    failedAgent: null,
  }
}

function applyAgentEvent(block: ActivityBlock, e: CaseEvent) {
  const id = String(e.agent_id)
  const p = e.payload
  if (!block.agents[id]) {
    block.order.push(id)
    block.agents[id] = emptyRun(id)
  }
  const run = block.agents[id]
  run.lastEvent = e
  const step = stepOf(e)
  if (step) run.steps.push(step)
  switch (e.type) {
    case 'AGENT_STARTED':
      run.status = 'running'
      run.round = Number(p.round)
      break
    case 'TOOL_CALLED':
      run.toolCalls += 1
      block.toolCalls += 1
      break
    case 'PERMISSION_DENIED':
      block.denied += 1
      block.notices.push({
        key: `n${e.seq}`,
        kind: 'denied',
        tone: 'danger',
        text: `${agentName(id)} tentou acessar ${deniedTarget(p)}. O backend negou (${denyReason(p.reason)}) e as permissões não mudaram.`,
      })
      break
    case 'SECURITY_EVENT':
      // SCOPE_VIOLATION_BLOCKED acompanha um PERMISSION_DENIED que já foi contado
      if (p.kind !== 'SCOPE_VIOLATION_BLOCKED') block.security += 1
      if (p.kind === 'INJECTION_SUSPECTED') {
        const refs = Array.isArray(p.out_of_scope_refs) && p.out_of_scope_refs.length > 0
        block.notices.push({
          key: `n${e.seq}`,
          kind: 'injection',
          tone: 'danger',
          text: `Um documento do cliente trazia instruções para os agentes${refs ? ` e citava ${(p.out_of_scope_refs as string[]).join(', ')}` : ''}. Ele foi tratado como dado, não como instrução.`,
        })
      }
      break
    case 'AGENT_COMPLETED':
      run.status = 'done'
      run.outputIds.push(String(p.output_id))
      break
    case 'TASK_REOPENED':
      run.status = 'reopened'
      run.reopenedBy = p.source === 'human' ? 'human' : 'review'
      break
    case 'EXECUTION_FAILED':
      run.status = 'failed'
      break
  }
}

function understood(it: NonNullable<CaseState['interpreted']>): string {
  const amount = it.requested_amount?.toLocaleString('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    maximumFractionDigits: 0,
  })
  const what = [it.purpose ?? 'crédito', it.crop ? `de ${it.crop}` : '', it.cycle ?? ''].filter(Boolean).join(' ')
  const client = (it.client_ref ?? 'informado').replace(/\.$/, '')
  return `Entendi: ${what}${amount ? ` no valor de ${amount}` : ''}, para o cliente ${client}.`
}
