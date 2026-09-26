import { useMemo, useState } from 'react'
import { AGENT_STATUS_LABEL, DOMAIN_LABEL, shortAgent } from '../format'
import type { AgentCardState, CaseEvent, CaseState } from '../types'

const DOMAINS = Object.keys(DOMAIN_LABEL)

interface Props {
  state: CaseState
  events: CaseEvent[]
  busy: boolean
  onRun: () => void
  onInput: (answers: Record<string, unknown>) => void
}

export function SquadBoard({ state, events, busy, onRun, onInput }: Props) {
  const reopened = events.filter((e) => e.type === 'TASK_REOPENED')
  return (
    <section className="card">
      <h2>2. Execução da squad</h2>
      {state.scope && (
        <p className="scope">
          CaseScope congelado: <code>{state.scope.client_ids.join(', ')}</code> · purpose <code>{state.scope.purpose}</code>
          <span className="tag ok">imutável durante o case</span>
        </p>
      )}
      {state.status === 'waiting_input' && state.missing_info && (
        <MissingInfoForm state={state} busy={busy} onInput={onInput} />
      )}
      {state.status === 'planned' && (
        <div className="row">
          <button disabled={busy} onClick={onRun}>
            Executar agentes
          </button>
          <span className="muted">Eligibility → Risk → Structuring → Review (coleta determinística; LLM não chama tools)</span>
        </div>
      )}
      {state.status === 'failed' && <div className="banner danger">Execução falhou (auditada): {state.error}</div>}

      <div className="agents">
        {state.agents.map((a) => (
          <AgentCard key={a.agent_id} agent={a} />
        ))}
      </div>
      {reopened.length > 0 && (
        <div className="banner info">
          Rework: Review reabriu <b>{shortAgent(String(reopened[0].agent_id))}</b> (rodada {String(reopened[0].payload.round)})
          por conta de {(reopened[0].payload.finding_ids as string[]).join(', ')}; dependentes reexecutados. Máximo de 1
          rodada.
        </div>
      )}

      <GovernancePanel state={state} events={events} />
      <Timeline events={events} />
    </section>
  )
}

function AgentCard({ agent }: { agent: AgentCardState }) {
  return (
    <article className={`agent ${agent.status}`}>
      <header>
        <strong>{agent.name}</strong>
        <span className={`tag ${agent.status}`}>{AGENT_STATUS_LABEL[agent.status]}</span>
      </header>
      <div className="muted small">
        rodada {agent.round} · {agent.tool_calls} tool calls · {agent.source_count} fontes ·{' '}
        {agent.denied_calls > 0 ? <b className="danger-text">{agent.denied_calls} negada(s)</b> : '0 negadas'}
      </div>
      <div className="domains">
        {agent.data_domains_accessed.length === 0 && <span className="muted small">nenhum domínio acessado</span>}
        {agent.data_domains_accessed.map((d) => (
          <span key={d} className="pill">
            {DOMAIN_LABEL[d] ?? d}
          </span>
        ))}
      </div>
      {agent.summary && <p className="small">{agent.summary}</p>}
    </article>
  )
}

interface Cell {
  allowed: number
  denied: number
}

function cellClass(c: Cell | undefined): string {
  if (!c) return 'none'
  if (c.denied && c.allowed) return 'mixed'
  return c.denied ? 'denied' : 'allowed'
}

function cellMark(c: Cell | undefined): string {
  if (!c) return '·'
  return `${c.allowed ? '✓' : ''}${c.denied ? '✗' : ''}`
}

function GovernancePanel({ state, events }: { state: CaseState; events: CaseEvent[] }) {
  const matrix = useMemo(() => {
    const m = new Map<string, Cell>()
    for (const e of events) {
      if (e.type !== 'PERMISSION_CHECKED' && e.type !== 'PERMISSION_DENIED') continue
      const key = `${e.agent_id}|${String(e.payload.resource_domain)}`
      const cell = m.get(key) ?? { allowed: 0, denied: 0 }
      if (e.type === 'PERMISSION_DENIED') cell.denied += 1
      else if (e.payload.allowed === true) cell.allowed += 1
      m.set(key, cell)
    }
    return m
  }, [events])
  const security = events.filter((e) => e.type === 'SECURITY_EVENT' || e.type === 'PERMISSION_DENIED')
  const fieldsHidden = useMemo(() => {
    const seen = new Set<string>()
    let total = 0
    for (const e of events) {
      if (e.type !== 'TOOL_CALLED' || typeof e.payload.fields_hidden !== 'number') continue
      const key = Array.isArray(e.payload.source_ids) ? e.payload.source_ids.join(',') : `seq-${e.seq}`
      if (seen.has(key)) continue
      seen.add(key)
      total += e.payload.fields_hidden
    }
    return total
  }, [events])

  return (
    <div className="governance">
      <h3>Governança e segurança</h3>
      <div className="badges">
        <span className="tag ok">permissões inalteradas</span>
        <span className="tag ok">LLM sem capability de acesso a dados</span>
        <span className="tag">{state.counters.permission_checks} checks</span>
        <span className={`tag ${state.counters.permission_denials ? 'danger' : ''}`}>
          {state.counters.permission_denials} negações
        </span>
        <span className={`tag ${state.counters.security_events ? 'danger' : ''}`}>
          {state.counters.security_events} eventos de segurança
        </span>
        <span className="tag">
          {state.report?.governance.fields_hidden_total ?? fieldsHidden} campos ocultados (field-level)
        </span>
      </div>
      <table className="matrix">
        <thead>
          <tr>
            <th>agente × domínio</th>
            {DOMAINS.map((d) => (
              <th key={d}>{DOMAIN_LABEL[d]}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {state.agents.map((a) => (
            <tr key={a.agent_id}>
              <td>{shortAgent(a.agent_id)}</td>
              {DOMAINS.map((d) => {
                const cell = matrix.get(`${a.agent_id}|${d}`)
                const title = cell ? `${cell.allowed} autorizado(s) · ${cell.denied} negado(s)` : 'não solicitado'
                return (
                  <td key={d} className={`cell ${cellClass(cell)}`} title={title}>
                    {cellMark(cell)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        ✓ acesso autorizado (user ∩ agent ∩ case_scope ∩ purpose ∩ policy) · ✗ negado pelo backend · · não solicitado.
        Structuring não recebe financials brutos: trabalha com o Risk Output compacto.
      </p>
      {security.length > 0 && (
        <ul className="security">
          {security.map((e) => (
            <li key={e.seq}>
              <span className={`tag ${e.type === 'PERMISSION_DENIED' ? 'danger' : 'warn'}`}>{e.type}</span>{' '}
              {e.type === 'PERMISSION_DENIED' ? (
                <>
                  <b>{shortAgent(e.agent_id)}</b> tentou <code>{String(e.payload.action)}</code> em{' '}
                  <code>{String(e.payload.resource_key)}</code> → negado (<code>{String(e.payload.reason)}</code>)
                  {e.payload.probe === true && <span className="muted"> · scope probe determinístico</span>}
                </>
              ) : (
                <>
                  <code>{String(e.payload.kind)}</code>
                  {e.payload.source_id != null && (
                    <>
                      {' '}
                      em <code>{String(e.payload.source_id)}</code>
                    </>
                  )}
                  {e.payload.target_client_id != null && (
                    <>
                      {' '}
                      · alvo <code>{String(e.payload.target_client_id)}</code> ({String(e.payload.reason)})
                    </>
                  )}
                  {Array.isArray(e.payload.out_of_scope_refs) && e.payload.out_of_scope_refs.length > 0 && (
                    <> · cita {(e.payload.out_of_scope_refs as string[]).join(', ')} (fora do escopo)</>
                  )}
                  {' · '}
                  permissões alteradas: <b>{String(e.payload.permissions_changed ?? false)}</b>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

const QUIET: ReadonlySet<string> = new Set(['PERMISSION_CHECKED', 'TOOL_CALLED'])

function Timeline({ events }: { events: CaseEvent[] }) {
  const [all, setAll] = useState(false)
  const shown = all ? events : events.filter((e) => !QUIET.has(e.type))
  return (
    <details className="timeline">
      <summary>
        Timeline de eventos ({events.length}){' '}
        <button type="button" className="ghost" onClick={(e) => (e.preventDefault(), setAll((v) => !v))}>
          {all ? 'ocultar checks/tool calls' : 'mostrar tudo'}
        </button>
      </summary>
      <ol>
        {shown.map((e) => (
          <li key={e.seq} className={e.type}>
            <span className="seq">#{e.seq}</span> <code>{e.type}</code>
            {e.agent_id && <span className="muted"> · {shortAgent(e.agent_id)}</span>}
            <span className="muted small"> {summarize(e)}</span>
          </li>
        ))}
      </ol>
    </details>
  )
}

function summarize(e: CaseEvent): string {
  const p = e.payload
  switch (e.type) {
    case 'TOOL_CALLED':
    case 'PERMISSION_CHECKED':
    case 'PERMISSION_DENIED':
      return `${String(p.action)} ${String(p.resource_domain)}:${String(p.resource_key)}${p.allowed === false ? ` — ${String(p.reason)}` : ''}`
    case 'LLM_CALLED': {
      if (p.ok === false) return `falhou: ${String(p.error)}`
      const u = p.usage as { model?: string; tokens_in?: number; tokens_out?: number; latency_ms?: number } | undefined
      return u ? `${u.model ?? ''} in=${u.tokens_in ?? 0} out=${u.tokens_out ?? 0} ${u.latency_ms ?? 0}ms` : ''
    }
    case 'REVIEW_ISSUE_FOUND':
      return `${String(p.finding_id)} ${String(p.code)} [${String(p.severity)}]`
    case 'TASK_REOPENED':
      return `rodada ${String(p.round)} · ${(p.finding_ids as string[] | undefined)?.join(', ') ?? ''}`
    case 'AGENT_COMPLETED':
      return `${String(p.output_id)} · ${String(p.tool_calls)} tool calls`
    case 'SECURITY_EVENT':
      return `${String(p.kind)} ${String(p.source_id ?? '')}`
    case 'OUTPUT_GUARD_APPLIED':
      return `${(p.codes as string[] | undefined)?.join(', ') ?? ''} · ${String(p.redactions ?? 0)} redações`
    case 'RESULT_CONSOLIDATED':
      return `${String(p.findings)} findings · ${String(p.alternatives)} alternativas · ${String(p.rework_rounds)} rework`
    case 'CASE_COMPLETED':
      return String(p.note ?? '')
    default:
      return Object.keys(p).length ? JSON.stringify(p).slice(0, 120) : ''
  }
}

function MissingInfoForm({
  state,
  busy,
  onInput,
}: {
  state: CaseState
  busy: boolean
  onInput: (answers: Record<string, unknown>) => void
}) {
  const info = state.missing_info!
  const [answers, setAnswers] = useState<Record<string, string>>({})
  return (
    <div className="banner warn">
      <p>
        <b>Informação necessária</b> ({info.reason}): {info.message}
      </p>
      {info.items.map((item) => (
        <label key={item} className="field">
          <span>{item}</span>
          <input value={answers[item] ?? ''} onChange={(e) => setAnswers({ ...answers, [item]: e.target.value })} />
        </label>
      ))}
      <button disabled={busy} onClick={() => onInput(answers)}>
        Enviar informação
      </button>
      <p className="muted small">
        A resposta é tratada como dado não confiável e não altera o CaseScope: se ela citar outro cliente, o acesso continua
        negado.
      </p>
    </div>
  )
}
