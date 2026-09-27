// Estado do workspace: várias conversas, cada uma com ramificações (branches). Cada branch é um case no backend.
// Cases ativos são acompanhados por polling em paralelo — times diferentes podem trabalhar ao mesmo tempo.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, api } from './api'
import type { LocalMessage } from './transcript'
import type { CaseEvent, CaseState, CaseStatus, HumanReviewRequest, Report } from './types'

export const USER_ID = 'analyst-001'
const POLL_MS = 1200
const STORAGE_KEY = 'agent-squads.conversations.v1'

export const ACTIVE: ReadonlySet<CaseStatus> = new Set(['interpreting', 'running', 'reviewing', 'consolidating'])

export interface Branch {
  id: string
  caseId: string | null
  prompt: string
  adversarial: boolean
  origin: 'new' | 'edit' | 'regenerate'
  createdAt: number
  error?: string
  local: LocalMessage[] // mensagens que só existem no cliente (recusas locais, textos do analista)
  inputs: string[] // respostas a pedidos de informação, na ordem em que foram enviadas
}

export interface Conversation {
  id: string
  createdAt: number
  branches: Branch[]
  active: number
}

export interface CaseData {
  state: CaseState | null
  events: CaseEvent[]
  lastSeq: number
  reports: Record<number, Report> // versões do relatório, pelo seq do RESULT_CONSOLIDATED
  missing: boolean // o backend não conhece mais o case (reiniciou: estado em memória)
}

const uid = () => Math.random().toString(36).slice(2, 10)

const newBranch = (prompt: string, adversarial: boolean, origin: Branch['origin']): Branch => ({
  id: uid(),
  caseId: null,
  prompt,
  adversarial,
  origin,
  createdAt: Date.now(),
  local: [],
  inputs: [],
})

// Texto que o analista acabou de enviar; some quando o evento correspondente (seq > sinceSeq) chega do backend.
export interface PendingMessage {
  text: string
  sinceSeq: number
}

function load(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Conversation[]) : []
  } catch {
    return []
  }
}

function save(conversations: Conversation[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations))
  } catch {
    /* armazenamento indisponível: a conversa só vive nesta aba */
  }
}

// Guarda cada versão do relatório: só quando o gate humano já foi aberto depois da consolidação
// (garante que `state.report` é o relatório daquela consolidação e não um estado intermediário).
function snapshotReports(prev: Record<number, Report>, state: CaseState, events: CaseEvent[]) {
  if (!state.report) return prev
  let consolidated = -1
  let gateAfter = false
  for (const e of events) {
    if (e.type === 'RESULT_CONSOLIDATED') {
      consolidated = e.seq
      gateAfter = false
    } else if (e.type === 'HUMAN_REVIEW_REQUIRED' && consolidated >= 0) gateAfter = true
  }
  if (consolidated < 0 || !gateAfter || prev[consolidated]) return prev
  return { ...prev, [consolidated]: state.report }
}

export function useWorkspace() {
  const [conversations, setConversations] = useState<Conversation[]>(load)
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [cases, setCases] = useState<Record<string, CaseData>>({})
  const [pending, setPending] = useState<Record<string, PendingMessage | null>>({}) // por branch
  const [error, setError] = useState<string | null>(null)
  const casesRef = useRef(cases)
  useEffect(() => {
    casesRef.current = cases
  }, [cases])
  const inFlight = useRef(new Set<string>())

  useEffect(() => save(conversations), [conversations])


  const current = conversations.find((c) => c.id === currentId) ?? null
  const branch = current ? current.branches[current.active] : null

  const updateBranch = useCallback((convId: string, branchId: string, fn: (b: Branch) => Branch) => {
    setConversations((cs) =>
      cs.map((c) => (c.id === convId ? { ...c, branches: c.branches.map((b) => (b.id === branchId ? fn(b) : b)) } : c)),
    )
  }, [])

  const refresh = useCallback(async (caseId: string) => {
    if (inFlight.current.has(caseId)) return
    inFlight.current.add(caseId)
    try {
      const after = casesRef.current[caseId]?.lastSeq ?? 0
      const [state, evs] = await Promise.all([api.getCase(caseId), api.events(caseId, after)])
      setCases((all) => {
        const prev = all[caseId] ?? { state: null, events: [], lastSeq: 0, reports: {}, missing: false }
        const fresh = evs.filter((e) => e.seq > prev.lastSeq)
        const events = fresh.length ? [...prev.events, ...fresh] : prev.events
        const lastSeq = events.length ? events[events.length - 1].seq : prev.lastSeq
        return {
          ...all,
          [caseId]: { state, events, lastSeq, reports: snapshotReports(prev.reports, state, events), missing: false },
        }
      })
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setCases((all) => ({
          ...all,
          [caseId]: { ...(all[caseId] ?? { state: null, events: [], lastSeq: 0, reports: {} }), missing: true },
        }))
      } else {
        setError((e as Error).message)
      }
    } finally {
      inFlight.current.delete(caseId)
    }
  }, [])

  // Ao abrir a página: busca o estado do case ativo de cada conversa (status na barra lateral, polling dos que rodam).
  const conversationsRef = useRef(conversations)
  useEffect(() => {
    conversationsRef.current = conversations
  }, [conversations])
  const didInit = useRef(false)
  useEffect(() => {
    if (didInit.current) return
    didInit.current = true
    for (const c of conversationsRef.current.slice(0, 30)) {
      const id = c.branches[c.active]?.caseId
      if (id) void refresh(id)
    }
  }, [refresh])

  // Polling: todos os cases em andamento (de qualquer conversa) + o case aberto, se ainda não foi carregado.
  const openCaseId = branch?.caseId ?? null
  useEffect(() => {
    const tick = () => {
      const all = casesRef.current
      for (const [id, data] of Object.entries(all)) {
        if (!data.missing && data.state && ACTIVE.has(data.state.status)) void refresh(id)
      }
    }
    const timer = setInterval(tick, POLL_MS)
    return () => clearInterval(timer)
  }, [refresh])

  useEffect(() => {
    if (openCaseId && !casesRef.current[openCaseId]) void refresh(openCaseId)
  }, [openCaseId, refresh])

  // Ações que mudam o case: chamam o backend e já buscam o estado novo.
  const call = useCallback(
    async (caseId: string, fn: () => Promise<CaseState>) => {
      setError(null)
      try {
        await fn()
      } catch (e) {
        setError((e as Error).message)
      }
      await refresh(caseId)
    },
    [refresh],
  )

  const startBranch = useCallback(
    async (convId: string, b: Branch, autoRun: boolean) => {
      setError(null)
      setPending((p) => ({ ...p, [b.id]: { text: b.prompt, sinceSeq: 0 } }))
      try {
        const st = await api.createCase({
          user_id: USER_ID,
          prompt: b.prompt,
          demo_options: { adversarial_document: b.adversarial },
        })
        updateBranch(convId, b.id, (x) => ({ ...x, caseId: st.case_id, error: undefined }))
        setCases((all) => ({ ...all, [st.case_id]: { state: st, events: [], lastSeq: 0, reports: {}, missing: false } }))
        await refresh(st.case_id)
        if (autoRun && st.status === 'planned') await call(st.case_id, () => api.run(st.case_id))
      } catch (e) {
        updateBranch(convId, b.id, (x) => ({ ...x, error: (e as Error).message }))
      } finally {
        setPending((p) => ({ ...p, [b.id]: null }))
      }
    },
    [call, refresh, updateBranch],
  )

  const startConversation = useCallback(
    (prompt: string, adversarial: boolean) => {
      const b = newBranch(prompt, adversarial, 'new')
      const conv: Conversation = { id: uid(), createdAt: Date.now(), branches: [b], active: 0 }
      setConversations((cs) => [conv, ...cs])
      setCurrentId(conv.id)
      void startBranch(conv.id, b, false)
    },
    [startBranch],
  )

  // Ramificação estilo ChatGPT: editar a demanda ou gerar de novo cria um case novo ao lado do anterior.
  const branchFrom = useCallback(
    (conv: Conversation, prompt: string, origin: 'edit' | 'regenerate') => {
      const base = conv.branches[conv.active]
      const b = newBranch(prompt, base.adversarial, origin)
      setConversations((cs) =>
        cs.map((c) => (c.id === conv.id ? { ...c, branches: [...c.branches, b], active: c.branches.length } : c)),
      )
      void startBranch(conv.id, b, origin === 'regenerate')
    },
    [startBranch],
  )

  const restartBranch = useCallback((convId: string, b: Branch) => void startBranch(convId, b, false), [startBranch])

  const selectBranch = useCallback((convId: string, index: number) => {
    setConversations((cs) => cs.map((c) => (c.id === convId ? { ...c, active: index } : c)))
  }, [])

  const addLocal = useCallback(
    (convId: string, branchId: string, messages: LocalMessage[]) =>
      updateBranch(convId, branchId, (b) => ({ ...b, local: [...b.local, ...messages] })),
    [updateBranch],
  )

  const provideInput = useCallback(
    (convId: string, b: Branch, answers: Record<string, string>) => {
      if (!b.caseId) return
      const caseId = b.caseId
      updateBranch(convId, b.id, (x) => ({ ...x, inputs: [...x.inputs, Object.values(answers).join(', ')] }))
      void call(caseId, () => api.provideInput(caseId, { answers }))
    },
    [call, updateBranch],
  )

  const humanReview = useCallback(
    async (b: Branch, body: HumanReviewRequest) => {
      if (!b.caseId) return
      const caseId = b.caseId
      const sinceSeq = casesRef.current[caseId]?.lastSeq ?? 0
      setPending((p) => ({ ...p, [b.id]: { text: body.comment, sinceSeq } }))
      await call(caseId, () => api.humanReview(caseId, body))
      setPending((p) => ({ ...p, [b.id]: null }))
    },
    [call],
  )

  const run = useCallback((caseId: string) => call(caseId, () => api.run(caseId)), [call])
  const retry = useCallback((caseId: string) => call(caseId, () => api.retry(caseId)), [call])

  const caseData = openCaseId ? (cases[openCaseId] ?? null) : null
  // título como nos chats: a demanda interpretada ("Custeio de soja, Fazenda Horizonte S.A."), senão o texto enviado
  const titleOf = useCallback(
    (conv: Conversation): string => {
      const b = conv.branches[conv.active]
      const it = b.caseId ? cases[b.caseId]?.state?.interpreted : null
      if (!it?.purpose) return b.prompt
      const what = `${it.purpose}${it.crop ? ` de ${it.crop}` : ''}`
      const title = it.client_ref ? `${what}, ${it.client_ref}` : what
      return title.charAt(0).toUpperCase() + title.slice(1)
    },
    [cases],
  )
  const statusOf = useCallback(
    (conv: Conversation): CaseStatus | 'creating' | 'error' | null => {
      const b = conv.branches[conv.active]
      if (!b.caseId) return b.error ? 'error' : 'creating'
      return cases[b.caseId]?.state?.status ?? null
    },
    [cases],
  )

  return useMemo(
    () => ({
      conversations,
      current,
      branch,
      caseData,
      pending: branch ? (pending[branch.id] ?? null) : null,
      error,
      setError,
      openConversation: setCurrentId,
      newChat: () => setCurrentId(null),
      startConversation,
      branchFrom,
      restartBranch,
      selectBranch,
      addLocal,
      provideInput,
      humanReview,
      run,
      retry,
      statusOf,
      titleOf,
    }),
    [
      conversations,
      current,
      branch,
      caseData,
      pending,
      error,
      startConversation,
      branchFrom,
      restartBranch,
      selectBranch,
      addLocal,
      provideInput,
      humanReview,
      run,
      retry,
      statusOf,
      titleOf,
    ],
  )
}

export type Workspace = ReturnType<typeof useWorkspace>
