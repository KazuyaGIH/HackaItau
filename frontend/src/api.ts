import type {
  AssistReply,
  CaseEvent,
  CaseState,
  CreateCaseRequest,
  EvidenceItem,
  HealthResponse,
  HumanReviewRequest,
  InputRequest,
  Metrics,
  Report,
} from './types'

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let code = 'http_error'
    let message = `${res.status} ${res.statusText}`
    try {
      const body = (await res.json()) as { detail?: { code?: string; message?: string } | string }
      if (typeof body.detail === 'string') message = body.detail
      else if (body.detail) {
        code = body.detail.code ?? code
        message = body.detail.message ?? message
      }
    } catch {
      /* corpo não-JSON */
    }
    throw new ApiError(res.status, code, message)
  }
  return (await res.json()) as T
}

const post = (url: string, body: unknown) =>
  fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const api = {
  health: () => fetch('/api/health').then(json<HealthResponse>),
  createCase: (body: CreateCaseRequest) => post('/api/cases', body).then(json<CaseState>),
  getCase: (id: string) => fetch(`/api/cases/${id}`).then(json<CaseState>),
  events: (id: string, after = 0) => fetch(`/api/cases/${id}/events?after=${after}`).then(json<CaseEvent[]>),
  provideInput: (id: string, body: InputRequest) => post(`/api/cases/${id}/input`, body).then(json<CaseState>),
  run: (id: string) => post(`/api/cases/${id}/run`, {}).then(json<CaseState>),
  retry: (id: string) => post(`/api/cases/${id}/retry`, {}).then(json<CaseState>),
  reply: (id: string, text: string) => post(`/api/cases/${id}/reply`, { text }).then(json<CaseState>),
  attach: (id: string, body: { user_id: string; filename: string; content_type: string; data_base64: string }) =>
    post(`/api/cases/${id}/attachments`, body).then(json<CaseState>),
  assist: (body: { user_id: string; text: string; case_id?: string | null }) =>
    post('/api/assist', body).then(json<AssistReply>),
  metrics: () => fetch('/api/metrics').then(json<Metrics>),
  report: (id: string) => fetch(`/api/cases/${id}/report`).then(json<Report>),
  evidence: (id: string, evidenceId: string) =>
    fetch(`/api/cases/${id}/evidence/${encodeURIComponent(evidenceId)}`).then(json<EvidenceItem>),
  humanReview: (id: string, body: HumanReviewRequest) =>
    post(`/api/cases/${id}/human-review`, body).then(json<CaseState>),
}
