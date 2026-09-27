// Estado do workspace: várias conversas, cada uma com ramificações (branches). Cada branch é um case no backend.
// Cases ativos são acompanhados por polling em paralelo — times diferentes podem trabalhar ao mesmo tempo.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, api } from './api'
import { localRefusal } from './guard'
import type { LocalMessage, Turn } from './transcript'
import type { AssistReply, CaseEvent, CaseState, CaseStatus, HumanReviewRequest, Report } from './types'

const POLL_MS = 1200
// conversas são de cada usuário: trocar de login mostra só as dele
const storageKey = (userId: string) => `agent-squads.conversations.v1.${userId}`

export const ACTIVE: ReadonlySet<CaseStatus> = new Set(['interpreting', 'running', 'reviewing', 'consolidating'])
export const MAX_FILE_BYTES = 2_000_000
export const ACCEPTED_FILES = '.pdf,.txt,.md,.csv,.json'

export interface Branch {
  id: string
  caseId: string | null
  prompt: string
  adversarial: boolean
  origin: 'new' | 'edit' | 'regenerate'
  createdAt: number
  error?: string
  creating?: boolean // o case está sendo aberto no backend
  local: LocalMessage[] // mensagens que só existem no cliente (respostas do assistente, recusas locais)
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

// Texto que o analista acabou de enviar; some quando o evento correspondente (seq > sinceSeq) chega do backend
// ou quando a resposta local do assistente entra na conversa.
export interface PendingMessage {
  text: string
  sinceSeq: number
  files: string[]
}

export interface SendOptions {
  target: string
  files: File[]
}

async function toBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer())
  let binary = ''
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  return btoa(binary)
}

const lk = () => `l-${Math.random().toString(36).slice(2, 10)}`

const userTurn = (text: string, files: string[] = []): Turn => ({ kind: 'user', key: `${lk()}-u`, role: 'chat', text, files })
const assistTurn = (reply: AssistReply): Turn => {
  const k = lk()
  return { kind: 'assistant', key: `${k}-a`, parts: [{ kind: 'assist', key: `${k}-p`, reply }], live: false }
}
const textReply = (message: string): AssistReply => ({ kind: 'clarify', message, bullets: [], citations: [], suggestions: [] })

function load(userId: string): Conversation[] {
  try {
    const raw = localStorage.getItem(storageKey(userId))
    return raw ? (JSON.parse(raw) as Conversation[]) : []
  } catch {
    return []
  }
}

function save(userId: string, conversations: Conversation[]) {
  try {
    localStorage.setItem(storageKey(userId), JSON.stringify(conversations))
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

export function useWorkspace(userId: string) {
  const [conversations, setConversations] = useState<Conversation[]>(() => load(userId))
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [cases, setCases] = useState<Record<string, CaseData>>({})
  const [pending, setPending] = useState<Record<string, PendingMessage | null>>({}) // por branch
  const [error, setError] = useState<string | null>(null)
  const casesRef = useRef(cases)
  useEffect(() => {
    casesRef.current = cases
  }, [cases])
  const inFlight = useRef(new Set<string>())

  useEffect(() => save(userId, conversations), [userId, conversations])


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

  const upload = useCallback(
    async (caseId: string, files: File[]) => {
      for (const f of files) {
        if (f.size > MAX_FILE_BYTES) {
          setError(`${f.name}: arquivo maior que 2 MB.`)
          continue
        }
        try {
          await api.attach(caseId, {
            user_id: userId,
            filename: f.name,
            content_type: f.type,
            data_base64: await toBase64(f),
          })
        } catch (e) {
          setError(`${f.name}: ${(e as Error).message}`)
        }
      }
      await refresh(caseId)
    },
    [refresh, userId],
  )

  const startBranch = useCallback(
    async (convId: string, b: Branch, autoRun: boolean, files: File[] = []) => {
      setError(null)
      updateBranch(convId, b.id, (x) => ({ ...x, prompt: b.prompt, creating: true, error: undefined }))
      setPending((p) => ({ ...p, [b.id]: { text: b.prompt, sinceSeq: 0, files: files.map((f) => f.name) } }))
      try {
        const st = await api.createCase({
          user_id: userId,
          prompt: b.prompt,
          demo_options: { adversarial_document: b.adversarial },
        })
        updateBranch(convId, b.id, (x) => ({ ...x, caseId: st.case_id, creating: false }))
        setCases((all) => ({ ...all, [st.case_id]: { state: st, events: [], lastSeq: 0, reports: {}, missing: false } }))
        if (files.length) await upload(st.case_id, files)
        await refresh(st.case_id)
        if (autoRun && st.status === 'planned') await call(st.case_id, () => api.run(st.case_id))
      } catch (e) {
        updateBranch(convId, b.id, (x) => ({ ...x, creating: false, error: (e as Error).message }))
      } finally {
        setPending((p) => ({ ...p, [b.id]: null }))
      }
    },
    [call, refresh, updateBranch, upload, userId],
  )

  const addLocal = useCallback(
    (convId: string, branchId: string, messages: LocalMessage[]) =>
      updateBranch(convId, branchId, (b) => ({ ...b, local: [...b.local, ...messages] })),
    [updateBranch],
  )

  const humanReview = useCallback(
    async (b: Branch, body: HumanReviewRequest) => {
      if (!b.caseId) return
      const caseId = b.caseId
      const sinceSeq = casesRef.current[caseId]?.lastSeq ?? 0
      setPending((p) => ({ ...p, [b.id]: { text: body.comment, sinceSeq, files: [] } }))
      await call(caseId, () => api.humanReview(caseId, body))
      setPending((p) => ({ ...p, [b.id]: null }))
    },
    [call],
  )

  // Toda mensagem do analista passa por aqui. O assistente do Orquestrador (backend) diz o que ela é:
  // uma demanda (abre a squad), uma resposta ou um ajuste para o case, ou uma pergunta que ele responde direto.
  const send = useCallback(
    async (text: string, opts: SendOptions) => {
      let conv = conversationsRef.current.find((c) => c.id === currentId) ?? null
      if (!conv) {
        const fresh = newBranch('', false, 'new')
        conv = { id: uid(), createdAt: Date.now(), branches: [fresh], active: 0 }
        const created = conv
        setConversations((cs) => [created, ...cs])
        setCurrentId(created.id)
      }
      const b = conv.branches[conv.active]
      const caseId = b.caseId
      const data = caseId ? casesRef.current[caseId] : null
      const state = data?.state ?? null
      const lastSeq = data?.lastSeq ?? 0
      const fileNames = opts.files.map((f) => f.name)
      const local = (...turns: Turn[]) =>
        addLocal(
          conv.id,
          b.id,
          turns.map((turn) => ({ afterSeq: lastSeq, turn })),
        )

      const refusal = text ? localRefusal(text, state) : null
      if (refusal) {
        local(userTurn(text, fileNames), assistTurn(textReply(refusal)))
        return
      }
      setError(null)
      setPending((p) => ({ ...p, [b.id]: { text, sinceSeq: lastSeq, files: fileNames } }))
      try {
        if (caseId && opts.files.length) await upload(caseId, opts.files)
        if (!text) return
        const reply = await api.assist({ user_id: userId, text, case_id: caseId })
        if (!caseId) {
          if (reply.kind === 'credit_demand') {
            await startBranch(conv.id, { ...b, prompt: text }, false, opts.files)
            return
          }
          const note = opts.files.length
            ? [assistTurn(textReply('Os anexos entram quando houver uma análise aberta: descreva a operação e envie de novo.'))]
            : []
          local(userTurn(text, fileNames), assistTurn(reply), ...note)
          return
        }
        if (reply.kind === 'adjustment') {
          setPending((p) => ({ ...p, [b.id]: null }))
          await humanReview(b, { decision: 'request_adjustment', comment: text, target_agent: opts.target })
        } else if (reply.kind === 'case_reply') {
          updateBranch(conv.id, b.id, (x) => ({ ...x, inputs: [...x.inputs, text] }))
          await call(caseId, () => api.reply(caseId, text))
        } else if (reply.kind === 'credit_demand') {
          local(
            userTurn(text, fileNames),
            assistTurn(
              textReply('Esta conversa já tem uma operação em análise. Para outra demanda, comece uma nova conversa.'),
            ),
          )
        } else {
          // com case aberto, os anexos já aparecem como cartões (DOCUMENT_ATTACHED): não repete os nomes aqui
          local(userTurn(text), assistTurn(reply))
        }
      } catch (e) {
        setError((e as Error).message)
      } finally {
        setPending((p) => ({ ...p, [b.id]: null }))
      }
    },
    [addLocal, call, currentId, humanReview, startBranch, updateBranch, upload, userId],
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

  // Apaga a conversa (todas as versões) deste navegador. Os cases continuam no backend, com a auditoria.
  const deleteConversation = useCallback((convId: string) => {
    const conv = conversationsRef.current.find((c) => c.id === convId)
    const caseIds = new Set((conv?.branches ?? []).map((b) => b.caseId).filter((id): id is string => !!id))
    setConversations((cs) => cs.filter((c) => c.id !== convId))
    setCurrentId((id) => (id === convId ? null : id))
    // para de acompanhar esses cases (polling)
    setCases((all) => Object.fromEntries(Object.entries(all).filter(([id]) => !caseIds.has(id))))
  }, [])

  const selectBranch = useCallback((convId: string, index: number) => {
    setConversations((cs) => cs.map((c) => (c.id === convId ? { ...c, active: index } : c)))
  }, [])

  const run = useCallback((caseId: string) => call(caseId, () => api.run(caseId)), [call])
  const retry = useCallback((caseId: string) => call(caseId, () => api.retry(caseId)), [call])

  const caseData = openCaseId ? (cases[openCaseId] ?? null) : null
  // título como nos chats: a demanda interpretada ("Custeio de soja, Fazenda Horizonte S.A."), senão o texto enviado
  const titleOf = useCallback(
    (conv: Conversation): string => {
      const b = conv.branches[conv.active]
      const it = b.caseId ? cases[b.caseId]?.state?.interpreted : null
      if (it?.purpose) {
        const what = `${it.purpose}${it.crop ? ` de ${it.crop}` : ''}`
        const title = it.client_ref ? `${what}, ${it.client_ref}` : what
        return title.charAt(0).toUpperCase() + title.slice(1)
      }
      const firstLocal = b.local.find((m) => m.turn.kind === 'user')?.turn
      return b.prompt || (firstLocal?.kind === 'user' ? firstLocal.text : '') || 'Nova conversa'
    },
    [cases],
  )
  const statusOf = useCallback(
    (conv: Conversation): CaseStatus | 'creating' | 'error' | null => {
      const b = conv.branches[conv.active]
      if (!b.caseId) return b.error ? 'error' : b.creating ? 'creating' : null
      return cases[b.caseId]?.state?.status ?? null
    },
    [cases],
  )

  return useMemo(
    () => ({
      conversations,
      current,
      userId,
      branch,
      caseData,
      pending: branch ? (pending[branch.id] ?? null) : null,
      error,
      setError,
      openConversation: setCurrentId,
      newChat: () => setCurrentId(null),
      send,
      branchFrom,
      restartBranch,
      deleteConversation,
      selectBranch,
      humanReview,
      run,
      retry,
      statusOf,
      titleOf,
    }),
    [
      userId,
      conversations,
      current,
      branch,
      caseData,
      pending,
      error,
      send,
      branchFrom,
      restartBranch,
      deleteConversation,
      selectBranch,
      humanReview,
      run,
      retry,
      statusOf,
      titleOf,
    ],
  )
}

export type Workspace = ReturnType<typeof useWorkspace>
