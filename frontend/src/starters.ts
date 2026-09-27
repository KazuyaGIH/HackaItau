// Demandas prontas do estado vazio do chat: cada uma demonstra uma parte do fluxo.
export const DEFAULT_PROMPT =
  'O cliente Fazenda Horizonte S.A. solicita R$ 50 milhões para custeio da safra de soja 2025/26.'

export interface Starter {
  label: string
  hint: string
  prompt: string
  adversarial: boolean
}

export const STARTERS: Starter[] = [
  {
    label: 'Custeio de soja da Fazenda Horizonte',
    hint: 'Fluxo completo, com revisão e retrabalho',
    prompt: DEFAULT_PROMPT,
    adversarial: false,
  },
  {
    label: 'O mesmo caso com um documento malicioso',
    hint: 'Mostra o bloqueio de prompt injection',
    prompt: DEFAULT_PROMPT,
    adversarial: true,
  },
  {
    label: 'Demanda sem cliente identificado',
    hint: 'O Orquestrador pede a informação que falta',
    prompt: 'Preciso de uma análise de R$ 20 milhões para custeio de milho safrinha.',
    adversarial: false,
  },
]
