// Vocabulário da squad na UI: papéis, times, passos de trabalho e rótulos legíveis.
// Tudo é derivado dos eventos (ids, códigos, contagens) — nenhum dado de cliente vem daqui.
import { DOMAIN_LABEL } from './format'
import type { CaseEvent } from './types'

export const ELIGIBILITY = 'agro_eligibility'
export const RISK = 'agro_credit_risk'
export const STRUCTURING = 'agro_structuring'
export const REVIEW = 'credit_review'

interface AgentMeta {
  name: string
  role: string
}

export const AGENT_META: Record<string, AgentMeta> = {
  [ELIGIBILITY]: { name: 'Elegibilidade', role: 'Checa documentação e enquadramento' },
  [RISK]: { name: 'Risco', role: 'Capacidade de pagamento e cenários de estresse' },
  [STRUCTURING]: { name: 'Estruturação', role: 'Propõe estruturas comparáveis' },
  [REVIEW]: { name: 'Revisor', role: 'Procura inconsistências e pede retrabalho' },
}

export const agentName = (id: string | null | undefined) => (id ? (AGENT_META[id]?.name ?? id) : 'Orquestrador')

// Agentes que o analista pode reabrir com um ajuste (o Revisor sempre roda depois).
export const ADJUSTABLE: Array<{ id: string; hint: string }> = [
  { id: STRUCTURING, hint: 'garantias, prazo, amortização, condicionantes' },
  { id: RISK, hint: 'riscos, mitigantes, leitura dos cenários' },
  { id: ELIGIBILITY, hint: 'documentação e enquadramento' },
]

// Times: o Orquestrador pode montar mais de um. Agentes desconhecidos caem em "Outros agentes".
export interface Team {
  id: string
  name: string
  agents: string[]
}

const TEAMS: Team[] = [
  { id: 'analysis', name: 'Time de análise de crédito', agents: [ELIGIBILITY, RISK, STRUCTURING] },
  { id: 'review', name: 'Time de revisão independente', agents: [REVIEW] },
]

export function teamsFor(agentIds: string[]): Team[] {
  const out: Team[] = []
  for (const t of TEAMS) {
    const agents = t.agents.filter((a) => agentIds.includes(a))
    if (agents.length) out.push({ ...t, agents })
  }
  const known = new Set(TEAMS.flatMap((t) => t.agents))
  const others = agentIds.filter((a) => !known.has(a))
  if (others.length) out.push({ id: 'others', name: 'Outros agentes', agents: others })
  return out
}

const TOOL_LABEL: Record<string, string> = {
  get_client_profile: 'Consultando o cadastro do cliente',
  get_client_financials: 'Consultando dados financeiros',
  get_agro_profile: 'Consultando o perfil agro',
  get_market_data: 'Consultando dados de mercado',
  get_available_documents: 'Listando documentos do cliente',
  search_policy: 'Buscando políticas internas',
  get_product_catalog: 'Consultando o catálogo de produtos',
  calculate_credit_metrics: 'Calculando métricas de crédito',
  run_stress_scenarios: 'Rodando cenários de estresse',
  get_historical_cases: 'Buscando casos históricos',
}

export const toolLabel = (action: unknown) => TOOL_LABEL[String(action)] ?? String(action)

export type StepKind =
  | 'start'
  | 'data'
  | 'calc'
  | 'policy'
  | 'llm'
  | 'denied'
  | 'security'
  | 'rejected'
  | 'reopen'
  | 'finding'
  | 'done'
  | 'fail'

export type Tone = 'neutral' | 'ok' | 'warn' | 'danger'

export interface Step {
  seq: number
  kind: StepKind
  text: string
  tone: Tone
}

const toolKind = (action: string): StepKind =>
  action.startsWith('calculate_') || action.startsWith('run_')
    ? 'calc'
    : action === 'search_policy' || action === 'get_historical_cases'
      ? 'policy'
      : 'data'

export const DENY_REASON: Record<string, string> = {
  client_out_of_case_scope: 'cliente fora do escopo do case',
  resource_not_authorized_for_agent: 'recurso não autorizado para este agente',
  resource_not_authorized_for_purpose: 'recurso não autorizado para esta finalidade',
  resource_not_authorized_for_user: 'recurso não autorizado para o usuário',
  tool_not_allowed_for_agent: 'ferramenta não permitida para este agente',
}

export const denyReason = (reason: unknown) => DENY_REASON[String(reason)] ?? String(reason)

// "Documentos de CLIENTE-999": o que o agente tentou acessar, sem expor dados.
export const deniedTarget = (p: Record<string, unknown>) =>
  `${DOMAIN_LABEL[String(p.resource_domain)] ?? String(p.resource_domain)}${p.resource_key ? ` de ${String(p.resource_key)}` : ''}`

export const SECURITY_LABEL: Record<string, string> = {
  INJECTION_SUSPECTED: 'Documento com instruções suspeitas (prompt injection). Foi tratado como dado, não como instrução.',
  SCOPE_VIOLATION_BLOCKED: 'Tentativa de acesso fora do escopo do case bloqueada.',
  SECRET_LEAK_BLOCKED: 'Vazamento de segredo bloqueado.',
  BOOTSTRAP_DENIED: 'Você não tem permissão para consultar este cliente.',
}

// Um passo legível por evento do agente; null = evento que não vira passo.
export function stepOf(e: CaseEvent): Step | null {
  const p = e.payload
  const step = (kind: StepKind, text: string, tone: Tone = 'neutral'): Step => ({ seq: e.seq, kind, text, tone })
  switch (e.type) {
    case 'AGENT_STARTED':
      return step('start', Number(p.round) > 1 ? `Recomeçou na rodada ${String(p.round)}` : 'Começou a trabalhar')
    case 'TOOL_CALLED':
      return step(toolKind(String(p.action)), toolLabel(p.action), 'ok')
    case 'PERMISSION_DENIED':
      return step('denied', `Acesso negado a ${deniedTarget(p)}: ${denyReason(p.reason)}`, 'danger')
    case 'SECURITY_EVENT':
      return p.kind === 'SCOPE_VIOLATION_BLOCKED' ? null : step('security', SECURITY_LABEL[String(p.kind)] ?? String(p.kind), 'danger')
    case 'LLM_CALLED':
      return p.ok === false ? step('fail', 'O modelo não respondeu', 'danger') : step('llm', 'Analisou as evidências')
    case 'OUTPUT_REJECTED':
      return step('rejected', p.retry ? 'Resposta fora do formato; devolvida ao modelo' : 'Resposta rejeitada pelo validador', 'warn')
    case 'GROUNDING_REJECTED':
      return step('rejected', 'Citações sem evidência descartadas', 'warn')
    case 'AGENT_COMPLETED':
      return step('done', 'Entregou o resultado', 'ok')
    case 'TASK_REOPENED':
      return step('reopen', p.source === 'human' ? 'Reaberto pelo seu ajuste' : 'Reaberto pelo Revisor', 'warn')
    case 'REVIEW_ISSUE_FOUND':
      return p.severity === 'high' || p.severity === 'medium'
        ? step('finding', `Apontou um problema${p.owner ? ` para ${agentName(String(p.owner))}` : ''}`, 'warn')
        : null
    case 'EXECUTION_FAILED':
      return step('fail', 'Parou com erro', 'danger')
    default:
      return null
  }
}

// O que o agente está fazendo agora, a partir do último evento dele.
export function currentActivity(last: CaseEvent | undefined): string {
  if (!last) return 'Na fila'
  switch (last.type) {
    case 'AGENT_STARTED':
    case 'TASK_REOPENED':
      return 'Coletando os dados autorizados'
    case 'TOOL_CALLED':
    case 'PERMISSION_CHECKED':
      return toolLabel(last.payload.action)
    case 'LLM_CALLED':
    case 'OUTPUT_REJECTED':
      return 'Validando o resultado'
    case 'REVIEW_STARTED':
      return 'Rodando os validadores'
    default:
      return 'Analisando as evidências'
  }
}

export const domainsText = (domains: string[]) => domains.map((d) => DOMAIN_LABEL[d] ?? d).join(', ')
