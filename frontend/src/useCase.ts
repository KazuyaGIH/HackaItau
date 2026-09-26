import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import type { CaseEvent, CaseState, CaseStatus, CreateCaseRequest, HumanReviewRequest } from './types'

export const POLL_MS = 1500

// Estados em que o backend ainda está trabalhando: só aqui vale a pena continuar o polling.
const ACTIVE: ReadonlySet<CaseStatus> = new Set(['interpreting', 'running', 'reviewing', 'consolidating'])

export function useCase() {
  const [state, setState] = useState<CaseState | null>(null)
  const [events, setEvents] = useState<CaseEvent[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const lastSeq = useRef(0)

  const refresh = useCallback(async (caseId: string) => {
    const [st, evs] = await Promise.all([api.getCase(caseId), api.events(caseId, lastSeq.current)])
    if (evs.length) {
      lastSeq.current = evs[evs.length - 1].seq
      setEvents((prev) => [...prev, ...evs])
    }
    setState(st)
    return st
  }, [])

  const call = useCallback(
    async (fn: () => Promise<CaseState>) => {
      setBusy(true)
      setError(null)
      try {
        const st = await fn()
        await refresh(st.case_id)
      } catch (e) {
        setError((e as Error).message)
      } finally {
        setBusy(false)
      }
    },
    [refresh],
  )

  const create = useCallback(
    (body: CreateCaseRequest) => {
      lastSeq.current = 0
      setEvents([])
      setState(null)
      return call(() => api.createCase(body))
    },
    [call],
  )
  const provideInput = useCallback(
    (answers: Record<string, unknown>) => state && call(() => api.provideInput(state.case_id, { answers })),
    [call, state],
  )
  const run = useCallback(() => state && call(() => api.run(state.case_id)), [call, state])
  const humanReview = useCallback(
    (body: HumanReviewRequest) => state && call(() => api.humanReview(state.case_id, body)),
    [call, state],
  )
  const reset = useCallback(() => {
    lastSeq.current = 0
    setEvents([])
    setState(null)
    setError(null)
  }, [])

  const caseId = state?.case_id
  const active = state ? ACTIVE.has(state.status) : false
  useEffect(() => {
    if (!caseId || !active) return
    const timer = setInterval(() => {
      refresh(caseId).catch((e: Error) => setError(e.message))
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [caseId, active, refresh])

  return { state, events, busy, error, active, create, provideInput, run, humanReview, reset }
}
