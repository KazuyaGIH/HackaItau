// O campo de mensagem nunca fala com um LLM fora do Orquestrador. Ele só abre cases e envia ajustes à squad;
// pedidos de decisão, perguntas sobre outros clientes e conversa livre recebem uma resposta fixa, local.
import type { CaseState } from './types'

const DECISION =
  /(?<!\p{L})(aprov[ae]r?|reprov[ae]r?|rejeit[ae]r?|negu?e o cr[eé]dito|negar o cr[eé]dito|liber[ae]r?|conced[ae]r?|autoriz[ae]r?)(?!\p{L})/iu
const CLIENT_ID = /\bCLIENTE-\d+\b/gi

export type Intent = { kind: 'create' } | { kind: 'adjust' } | { kind: 'reply'; text: string }

export function classify(text: string, state: CaseState | null): Intent {
  if (DECISION.test(text)) {
    return {
      kind: 'reply',
      text:
        state?.status === 'human_review_required'
          ? 'A squad não aprova nem rejeita crédito. Para registrar a sua decisão, use "Aprovar para a próxima etapa" logo acima; para mudar a análise, descreva o ajuste.'
          : 'Não posso aprovar, rejeitar ou liberar crédito: decisões materiais são sempre humanas. Posso montar uma squad para analisar a operação, e no final a decisão fica com você.',
    }
  }
  if (!state) return { kind: 'create' }

  const scope = new Set(state.scope?.client_ids ?? [])
  const others = [...new Set((text.match(CLIENT_ID) ?? []).map((c) => c.toUpperCase()))].filter((c) => !scope.has(c))
  if (others.length) {
    return {
      kind: 'reply',
      text: `Este case está restrito a ${[...scope].join(', ') || 'um cliente'} e não consulta ${others.join(', ')}. Para outro cliente, comece um novo chat; o acesso continua limitado às suas permissões.`,
    }
  }
  if (state.status === 'human_review_required') return { kind: 'adjust' }
  return {
    kind: 'reply',
    text: 'Neste momento eu só sigo o fluxo da squad. Quando o relatório estiver pronto, você pode pedir ajustes por aqui ou aprovar a análise. Para outra demanda, comece um novo chat.',
  }
}
