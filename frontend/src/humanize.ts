// Códigos do relatório em português de gente. Código desconhecido vira texto com espaços, nunca some.
import { agentName } from './squad'

const TERMS: Record<string, string> = {
  // amortização
  bullet_post_harvest: 'parcela única após a colheita',
  two_installments_post_harvest: 'duas parcelas após a colheita',
  monthly: 'parcelas mensais',
  semiannual: 'parcelas semestrais',
  custom: 'cronograma sob medida',
  // garantias e condicionantes
  penhor_safra: 'penhor da safra',
  aval_socios: 'aval dos sócios',
  cpr_financeira: 'CPR financeira',
  cpr_fisica: 'CPR física',
  seguro_agricola: 'seguro agrícola',
  alienacao_fiduciaria: 'alienação fiduciária',
  hipoteca: 'hipoteca',
  cessao_recebiveis: 'cessão de recebíveis',
  comprovacao_area_plantada: 'comprovação da área plantada',
  // riscos
  PRICE_PRODUCTIVITY_SENSITIVITY: 'sensibilidade a preço e produtividade',
  PRO_FORMA_LEVERAGE: 'alavancagem pró-forma',
  GEO_CROP_CONCENTRATION: 'concentração em uma cultura e uma região',
  PRICE_VOLATILITY: 'volatilidade do preço',
}

export const term = (code: string) => TERMS[code] ?? code.replace(/_/g, ' ').toLowerCase()
export const terms = (codes: string[]) => codes.map(term).join(', ')

const ASSUMPTION: Record<string, string> = {
  planted_area_hectares: 'Área plantada',
  productivity: 'Produtividade',
  price: 'Preço de referência',
  cost_per_hectare: 'Custo por hectare',
  requested_amount: 'Valor solicitado',
  net_debt: 'Dívida líquida',
  ebitda: 'EBITDA',
  PRODUCTIVITY_ABOVE_HISTORY: 'Produtividade acima do histórico',
}

export const assumptionName = (name: string) => ASSUMPTION[name] ?? term(name)

const brl = (v: number) =>
  Math.abs(v) >= 1e6
    ? `R$ ${(v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} milhões`
    : v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })

export function assumptionValue(value: unknown, unit: string | null): string {
  if (typeof value !== 'number') return String(value ?? '—')
  if (unit === 'BRL') return brl(value)
  const n = value.toLocaleString('pt-BR', { maximumFractionDigits: 2 })
  if (unit === 'BRL/saca') return `R$ ${n} por saca`
  if (unit === 'BRL/ha') return `R$ ${n} por hectare`
  return unit ? `${n} ${unit}` : n
}

const WARNING: Record<string, string> = {
  numero_no_texto_divergente_do_calc: 'um número citado no texto não bate com o cálculo',
}

// "[agro_credit_risk] numero_no_texto_divergente_do_calc:1,0x" → "Risco: um número citado no texto não bate com o cálculo (1,0x)"
export function readableItem(text: string): string {
  const m = /^\[(\w+)\]\s+(\w+)(?::(.*))?$/.exec(text.trim())
  if (!m) return text
  const [, agent, code, detail] = m
  return `${agentName(agent)}: ${WARNING[code] ?? code.replace(/_/g, ' ')}${detail ? ` (${detail})` : ''}`
}

export const coverageText = (v: number) => `${v.toLocaleString('pt-BR', { maximumFractionDigits: 2, minimumFractionDigits: 2 })}x`
export const money = brl
