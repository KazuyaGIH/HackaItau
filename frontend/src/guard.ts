// Recusas que não precisam nem ir ao backend: pedidos de decisão e menções a outro cliente.
// O resto do texto é lido pelo assistente do Orquestrador (/api/assist), que nunca chama um LLM fora da squad.
import type { CaseState } from './types'

const DECISION =
  /(?<!\p{L})(aprov[ae]r?|reprov[ae]r?|rejeit[ae]r?|negu?e o cr[eé]dito|negar o cr[eé]dito|liber[ae]r?|conced[ae]r?|autoriz[ae]r?)(?!\p{L})/iu
const CLIENT_ID = /\bCLIENTE-\d+\b/gi

export function localRefusal(text: string, state: CaseState | null): string | null {
  if (DECISION.test(text)) {
    return state?.status === 'human_review_required'
      ? 'A squad não aprova nem rejeita crédito. Para registrar a sua decisão, use "Aprovar para a próxima etapa" logo acima; para mudar a análise, descreva o ajuste.'
      : 'Não posso aprovar, rejeitar ou liberar crédito: decisões materiais são sempre humanas. Posso montar uma squad para analisar a operação, e no final a decisão fica com você.'
  }
  const scope = new Set(state?.scope?.client_ids ?? [])
  if (!scope.size) return null
  const others = [...new Set((text.match(CLIENT_ID) ?? []).map((c) => c.toUpperCase()))].filter((c) => !scope.has(c))
  if (others.length) {
    return `Este case está restrito a ${[...scope].join(', ')} e não consulta ${others.join(', ')}. Para outro cliente, comece uma nova conversa; o acesso continua limitado às suas permissões.`
  }
  return null
}
