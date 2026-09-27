// Resposta do Orquestrador ao final de uma execução, escrita a partir do relatório (código, sem LLM).
import { CLASSIFICATION_LABEL, brl, num } from './format'
import type { Report } from './types'

const ASSUMPTION_LABEL: Record<string, string> = {
  productivity: 'produtividade',
  price: 'preço de referência',
  planted_area_hectares: 'área plantada',
  cost_per_hectare: 'custo por hectare',
}

export function answerLines(r: Report, opts: { skipRework?: boolean } = {}): string[] {
  const lines: string[] = []
  const base = r.stress_scenarios.find((s) => Object.keys(s.shocks).length === 0)
  if (base) {
    lines.push(
      `No cenário base, a geração de caixa cobre ${num(base.coverage, 2)}x o valor pedido (${CLASSIFICATION_LABEL[base.classification] ?? base.classification}).`,
    )
  }
  const stressed = r.stress_scenarios.filter((s) => Object.keys(s.shocks).length > 0)
  const weak = stressed.filter((s) => s.classification === 'insufficient' || s.classification === 'attention_required')
  if (stressed.length) {
    lines.push(
      weak.length
        ? `Em ${weak.length} de ${stressed.length} cenários de estresse a cobertura fica abaixo do exigido pela política.`
        : `Nos ${stressed.length} cenários de estresse a cobertura se mantém dentro da política.`,
    )
  }
  if (r.alternatives.length) {
    lines.push(`${r.alternatives.length} estruturas alternativas, comparáveis e sem preferência do sistema.`)
  }
  for (const a of opts.skipRework ? [] : r.assumptions.filter((x) => x.changed_in_rework)) {
    lines.push(
      `O Revisor corrigiu uma premissa: ${ASSUMPTION_LABEL[a.name] ?? a.name} de ${num(a.previous_value)} para ${num(a.value)}${a.unit ? ` ${a.unit}` : ''}.`,
    )
  }
  const open = r.missing_data.length + r.uncertainties.length
  if (open) lines.push(`${open} pendência${open > 1 ? 's' : ''} ou incerteza${open > 1 ? 's' : ''} registrada${open > 1 ? 's' : ''} no relatório.`)
  if (r.review.open_count) {
    lines.push(`${r.review.open_count} achado${r.review.open_count > 1 ? 's' : ''} da revisão continua${r.review.open_count > 1 ? 'm' : ''} aberto${r.review.open_count > 1 ? 's' : ''}.`)
  }
  return lines
}

// O que um ajuste mudou em relação à versão anterior do relatório (estruturas: garantias, condições, prazo, valor).
export function adjustmentLines(prev: Report, next: Report): string[] {
  const out: string[] = []
  const before = new Map(prev.alternatives.map((a) => [a.id, a]))
  let rewritten = 0
  for (const a of next.alternatives) {
    const p = before.get(a.id)
    if (!p) {
      out.push(`Nova estrutura na comparação: ${a.name}.`)
      continue
    }
    const changes: string[] = []
    const diff = (label: string, now: string[], was: string[]) => {
      const added = now.filter((x) => !was.includes(x))
      const removed = was.filter((x) => !now.includes(x))
      if (added.length) changes.push(`${label} incluem ${added.join(', ')}`)
      if (removed.length) changes.push(`${label} não incluem mais ${removed.join(', ')}`)
    }
    diff('garantias', a.guarantees, p.guarantees)
    diff('condicionantes', a.conditions, p.conditions)
    if (a.tenor_months !== p.tenor_months) changes.push(`prazo de ${p.tenor_months} para ${a.tenor_months} meses`)
    if (a.amount !== p.amount) changes.push(`valor de ${brl(p.amount)} para ${brl(a.amount)}`)
    if (a.amortization !== p.amortization) changes.push(`amortização agora ${a.amortization}`)
    if (changes.length) out.push(`${a.name}: ${changes.join('; ')}.`)
    else if (a.rationale !== p.rationale || a.when_it_fits !== p.when_it_fits) rewritten += 1
  }
  for (const p of prev.alternatives) {
    if (!next.alternatives.some((a) => a.id === p.id)) out.push(`A estrutura ${p.name} saiu da comparação.`)
  }
  if (!out.length) {
    out.push(
      rewritten
        ? `Valores, prazos e garantias não mudaram; o racional de ${rewritten} estrutura${rewritten > 1 ? 's' : ''} foi reescrito.`
        : 'Valores, prazos e garantias das estruturas não mudaram; o Revisor conferiu o resultado de novo.',
    )
  }
  return out
}
