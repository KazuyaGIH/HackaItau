import { Ban, Check, Minus, ShieldAlert } from 'lucide-react'
import { useMemo, useState } from 'react'
import { DOMAIN_LABEL } from '../format'
import { SECURITY_LABEL, agentName, deniedTarget, denyReason } from '../squad'
import type { CaseEvent, CaseState } from '../types'

const DOMAINS = Object.keys(DOMAIN_LABEL)

interface Cell {
  allowed: number
  denied: number
}

function CellMark({ cell }: { cell: Cell | undefined }) {
  if (!cell) return <Minus size={12} className="none" />
  return (
    <>
      {cell.allowed > 0 && <Check size={14} />}
      {cell.denied > 0 && <Ban size={13} />}
    </>
  )
}

const cellClass = (c: Cell | undefined) => (!c ? 'none' : c.denied && c.allowed ? 'mixed' : c.denied ? 'denied' : 'allowed')

// Auditoria: quem acessou o quê (agente x domínio de dados) e todo evento de segurança do case.
export function GovernancePanel({ state, events }: { state: CaseState; events: CaseEvent[] }) {
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
  const security = events.filter(
    (e) => e.type === 'PERMISSION_DENIED' || (e.type === 'SECURITY_EVENT' && e.payload.kind !== 'SCOPE_VIOLATION_BLOCKED'),
  )
  const c = state.counters

  return (
    <div className="governance">
      <p className="lede">
        Cada agente herda as permissões de <strong>{state.user_id}</strong> e só acessa o que a tarefa pede. O modelo não
        tem acesso direto a dados: toda consulta passa pelo backend, que autoriza e registra.
      </p>
      <dl className="stat-row">
        <div>
          <dt>Verificações de permissão</dt>
          <dd className="num">{c.permission_checks}</dd>
        </div>
        <div>
          <dt>Acessos negados</dt>
          <dd className={`num${c.permission_denials ? ' danger-text' : ''}`}>{c.permission_denials}</dd>
        </div>
        <div>
          <dt>Alertas de segurança</dt>
          <dd className={`num${c.security_events ? ' danger-text' : ''}`}>{c.security_events}</dd>
        </div>
        <div>
          <dt>Campos ocultados</dt>
          <dd className="num">{state.report?.governance.fields_hidden_total ?? 0}</dd>
        </div>
      </dl>

      <h4>Acessos por agente</h4>
      <div className="table-scroll">
        <table className="matrix">
          <thead>
            <tr>
              <th />
              {DOMAINS.map((d) => (
                <th key={d}>{DOMAIN_LABEL[d]}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {state.agents.map((a) => (
              <tr key={a.agent_id}>
                <th>{agentName(a.agent_id)}</th>
                {DOMAINS.map((d) => {
                  const cell = matrix.get(`${a.agent_id}|${d}`)
                  const title = cell ? `${cell.allowed} autorizado(s), ${cell.denied} negado(s)` : 'não solicitado'
                  return (
                    <td key={d} className={`cell ${cellClass(cell)}`} title={title}>
                      <CellMark cell={cell} />
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        Autorizado quando usuário, agente, escopo do case, finalidade e política permitem ao mesmo tempo. Estruturação não
        recebe dados financeiros brutos: trabalha com o resultado compacto do Risco.
      </p>

      {security.length > 0 && (
        <>
          <h4>Eventos de segurança</h4>
          <ul className="security-list">
            {security.map((e) => (
              <li key={e.seq}>
                {e.type === 'PERMISSION_DENIED' ? <Ban size={15} /> : <ShieldAlert size={15} />}
                <span>
                  {e.type === 'PERMISSION_DENIED'
                    ? `${agentName(e.agent_id)} tentou acessar ${deniedTarget(e.payload)}: negado (${denyReason(e.payload.reason)}).`
                    : `${SECURITY_LABEL[String(e.payload.kind)] ?? String(e.payload.kind)}${e.payload.source_id ? ` Fonte: ${String(e.payload.source_id)}.` : ''}`}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

const QUIET: ReadonlySet<string> = new Set(['PERMISSION_CHECKED', 'TOOL_CALLED'])

export function Timeline({ events }: { events: CaseEvent[] }) {
  const [all, setAll] = useState(false)
  const shown = all ? events : events.filter((e) => !QUIET.has(e.type))
  return (
    <section className="timeline">
      <div className="timeline-head">
        <h4>Registro de eventos</h4>
        <button type="button" className="link" onClick={() => setAll((v) => !v)}>
          {all ? 'Ocultar verificações e consultas' : `Mostrar todos os ${events.length} eventos`}
        </button>
      </div>
      <ol>
        {shown.map((e) => (
          <li key={e.seq} className={e.type}>
            <span className="seq">{e.seq}</span>
            <span className="type">{e.type}</span>
            {e.agent_id && <span className="who">{agentName(e.agent_id)}</span>}
            <span className="what" title={summarize(e)}>
              {summarize(e)}
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}

function summarize(e: CaseEvent): string {
  const p = e.payload
  switch (e.type) {
    case 'TOOL_CALLED':
    case 'PERMISSION_CHECKED':
    case 'PERMISSION_DENIED':
      return `${String(p.action)} ${String(p.resource_domain)}:${String(p.resource_key)}${p.allowed === false ? ` — ${String(p.reason)}` : ''}`
    case 'OUTPUT_REJECTED': {
      const problems = Array.isArray(p.problems) ? (p.problems as unknown[]).map(String) : []
      return `${p.retry ? 'devolvido ao modelo para correção' : 'rejeitado (falha)'}: ${problems.join(' | ')}`
    }
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
