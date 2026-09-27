import type { AgentStatus, CaseStatus, Severity } from './types'

export const brl = (v: number | null | undefined) =>
  v == null ? '—' : v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })

export const num = (v: unknown, digits = 2) =>
  typeof v === 'number' ? v.toLocaleString('pt-BR', { maximumFractionDigits: digits }) : String(v ?? '—')

export const pct = (v: number) => `${v > 0 ? '+' : ''}${Math.round(v * 100)}%`

export const STATUS_LABEL: Record<CaseStatus, string> = {
  created: 'Criado',
  interpreting: 'Interpretando demanda',
  waiting_input: 'Aguardando informação',
  planned: 'Planejado — pronto para executar',
  running: 'Executando agentes',
  reviewing: 'Em revisão',
  consolidating: 'Consolidando',
  human_review_required: 'Pronto para revisão humana',
  completed_demo: 'Etapa concluída (demo)',
  failed: 'Falhou',
}

export const AGENT_STATUS_LABEL: Record<AgentStatus, string> = {
  selected: 'selecionado',
  waiting: 'aguardando',
  running: 'executando',
  completed: 'concluído',
  reopened: 'reaberto',
  blocked: 'bloqueado',
  failed: 'falhou',
}

export const SEVERITY_ORDER: Record<Severity, number> = { high: 0, medium: 1, low: 2, info: 3 }

export const CLASSIFICATION_LABEL: Record<string, string> = {
  comfortable: 'confortável',
  reduced_buffer: 'folga reduzida',
  attention_required: 'requer atenção',
  insufficient: 'insuficiente',
}

export const DOMAIN_LABEL: Record<string, string> = {
  client_profile: 'Cadastro',
  client_financials: 'Financials',
  agro_profile: 'Perfil agro',
  documents: 'Documentos',
  market_data: 'Mercado',
  product_catalog: 'Catálogo',
  knowledge: 'Políticas/KB',
  calculations: 'Cálculos',
}

export const shortAgent = (id: string | null | undefined) =>
  ({
    agro_eligibility: 'Elegibilidade',
    agro_credit_risk: 'Risco',
    agro_structuring: 'Estruturação',
    credit_review: 'Revisor',
  })[id ?? ''] ?? (id ?? 'orquestrador')

export const ELIGIBILITY_LABEL: Record<string, string> = {
  ready: 'pronto para seguir',
  ready_with_warnings: 'pronto, com alertas',
  blocked: 'bloqueado: falta informação',
}

export const REVIEW_STATUS_LABEL: Record<string, string> = {
  passed: 'aprovada',
  passed_with_findings: 'aprovada com ressalvas',
  rework_required: 'retrabalho necessário',
}

// Códigos técnicos (ex.: avisos do validador) em texto legível, sem esconder o código original.
export const humanizeCode = (code: string) => code.replace(/_/g, ' ').replace(':', ' — ')
