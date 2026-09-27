// Leitura do comparativo squad × generalista (GET /api/benchmarks/latest), usada na tela de entrada
// (versão completa) e em Desempenho dos agentes (resumo). Nada aqui chama o LLM.
import { useEffect, useState } from 'react'
import { api } from './api'
import type { BenchmarkSummary } from './types'

export type Group = BenchmarkSummary['groups'][number]

export const decimal = (v: number, digits = 1) => v.toLocaleString('pt-BR', { maximumFractionDigits: digits })
export const usd = (v: number | null, digits = 3) =>
  v === null ? 'indisponível' : `US$ ${v.toLocaleString('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`
export const cost = (g: Group) => (g.usage_complete ? g.total_cost_usd : null)
export const perfect = (g: Group) => g.runs > 0 && g.automatic_passes === g.runs

const MODEL_NAME: Array<[RegExp, string]> = [
  [/^gpt-4\.1-mini(?:-|$)/, 'GPT-4.1 mini'],
  [/^gpt-4\.1(?:-|$)/, 'GPT-4.1'],
  [/^gpt-5\.2(?:-|$)/, 'GPT-5.2'],
  [/^gpt-5\.4(?:-|$)/, 'GPT-5.4'],
]
const EFFORT: Record<string, string> = { low: 'raciocínio baixo', medium: 'raciocínio médio', high: 'raciocínio alto' }

// ordem das linhas: do modelo menor ao maior; desconhecidos no fim
export const modelRank = (g: Group) => {
  const i = MODEL_NAME.findIndex(([re]) => re.test(g.model))
  return i < 0 ? MODEL_NAME.length : i
}
export const modelName = (g: Group) => MODEL_NAME.find(([re]) => re.test(g.model))?.[1] ?? g.model
export const effortName = (g: Group) => (g.reasoning_effort ? EFFORT[g.reasoning_effort] ?? g.reasoning_effort : null)
export const configName = (g: Group) => [modelName(g), effortName(g)].filter(Boolean).join(' · ')
// versão curta para rótulos de gráfico: "GPT-5.4 · alto"
export const shortConfig = (g: Group) =>
  [modelName(g), g.reasoning_effort ? effortName(g)!.replace('raciocínio ', '') : null].filter(Boolean).join(' · ')
export const archName = (g: Group) => (g.architecture === 'squad' ? 'Squad' : 'Generalista')

// a configuração mais barata de uma arquitetura que passou em todos os casos (com custo conhecido)
export function cheapestPerfect(data: BenchmarkSummary, arch: Group['architecture']): Group | null {
  const ok = data.groups.filter((g) => g.architecture === arch && perfect(g) && cost(g) !== null)
  return ok.sort((a, b) => cost(a)! - cost(b)!)[0] ?? null
}

// o outro lado com o mesmo modelo e esforço: a comparação que isola a arquitetura
export const counterpart = (data: BenchmarkSummary, g: Group) =>
  data.groups.find(
    (o) => o.architecture !== g.architecture && o.model === g.model && (o.reasoning_effort ?? null) === (g.reasoning_effort ?? null),
  ) ?? null

// comparações só valem com o benchmark completo e a mesma amostra dos dois lados
export const comparable = (data: BenchmarkSummary, a: Group, b: Group) =>
  data.status === 'complete' && a.runs > 0 && a.runs === b.runs

export interface Headline {
  squad: Group
  generalist: Group
  costRatio: number | null // quantas vezes o generalista custou mais
  timeRatio: number // quantas vezes o generalista demorou mais
}

// "quanto custa chegar a 8/8": a squad mais barata com todos os casos contra o generalista mais barato com todos
export function headline(data: BenchmarkSummary): Headline | null {
  const squad = cheapestPerfect(data, 'squad')
  const generalist = cheapestPerfect(data, 'generalist')
  if (!squad || !generalist || !comparable(data, squad, generalist)) return null
  const sc = cost(squad)!
  const gc = cost(generalist)!
  return {
    squad,
    generalist,
    costRatio: sc > 0 ? gc / sc : null,
    timeRatio: squad.mean_latency_seconds > 0 ? generalist.mean_latency_seconds / squad.mean_latency_seconds : 0,
  }
}

export function useBenchmark(refresh = 0) {
  const [data, setData] = useState<BenchmarkSummary | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let active = true
    api.benchmark().then(
      (r) => {
        if (!active) return
        setData(r.benchmark)
        setError(false)
        setLoading(false)
      },
      () => {
        if (!active) return
        setError(true)
        setLoading(false)
      },
    )
    return () => {
      active = false
    }
  }, [refresh])
  return { data, error, loading }
}
