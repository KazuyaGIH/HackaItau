import { CLASSIFICATION_LABEL, DOMAIN_LABEL, SEVERITY_ORDER, brl, num, pct, shortAgent } from '../format'
import type { Alternative, Finding, Report, ReportItem } from '../types'
import { Chips } from './SourceChip'

interface Props {
  caseId: string
  report: Report
}

export function ReportView({ caseId, report }: Props) {
  const r = report
  return (
    <section className="card report">
      <h2>3. Relatório para revisão humana</h2>
      <div className="banner info">
        <b>{r.decision_status}</b> · {r.disclaimer}
      </div>
      {r.llm_mode !== 'real' && (
        <div className="banner warn">
          LLM em modo <b>{r.llm_mode}</b>: interpretação qualitativa por roteiro determinístico (ScriptedFallback). Cálculos,
          fontes e governança são reais. Configure <code>LLM_API_KEY</code> para a demo com LLM.
        </div>
      )}

      <dl className="summary">
        <div>
          <dt>Cliente</dt>
          <dd>{r.client_id}</dd>
        </div>
        <div>
          <dt>Valor solicitado</dt>
          <dd>{brl(r.summary.requested_amount)}</dd>
        </div>
        <div>
          <dt>Finalidade / cultura</dt>
          <dd>
            {r.summary.purpose ?? '—'} / {r.summary.crop ?? '—'}
          </dd>
        </div>
        <div>
          <dt>Eligibility</dt>
          <dd>{r.summary.eligibility_status}</dd>
        </div>
        <div>
          <dt>Alternativas</dt>
          <dd>{r.summary.alternatives_count}</dd>
        </div>
        <div>
          <dt>Rework</dt>
          <dd>{r.summary.rework_rounds}</dd>
        </div>
      </dl>

      <Section title="Fatos" items={r.facts} caseId={caseId} />

      <h3>Cálculos determinísticos</h3>
      <div className="calcs">
        {r.calculations.map((c) => (
          <article key={c.calculation_id} className="calc">
            <header>
              <Chips caseId={caseId} ids={[c.calculation_id]} />
              <span>{c.name}</span>
              {c.classification && <span className="tag">{CLASSIFICATION_LABEL[c.classification] ?? c.classification}</span>}
            </header>
            <pre className="formula">{c.formula}</pre>
            <table className="kv">
              <tbody>
                {Object.entries(c.outputs).map(([k, v]) => (
                  <tr key={k}>
                    <td>{k}</td>
                    <td>
                      {typeof v === 'object' && v !== null ? (
                        <span className="muted small">
                          {Array.isArray(v) ? `${v.length} itens` : 'objeto'} — abrir o ID acima
                        </span>
                      ) : (
                        <b>{num(v, 4)}</b>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted small">
              entradas: {Object.keys(c.inputs).join(', ')} · thresholds: <Chips caseId={caseId} ids={c.thresholds_source_ids} />
            </p>
          </article>
        ))}
      </div>

      <h3>Premissas</h3>
      <table className="table">
        <thead>
          <tr>
            <th>premissa</th>
            <th>valor</th>
            <th>origem</th>
            <th>fonte</th>
            <th>justificativa</th>
          </tr>
        </thead>
        <tbody>
          {r.assumptions.map((a) => (
            <tr key={a.name} className={a.changed_in_rework ? 'changed' : ''}>
              <td>{a.name}</td>
              <td>
                {num(a.value)} {a.unit ?? ''}
                {a.changed_in_rework && (
                  <span className="tag warn" title="alterada no rework">
                    era {num(a.previous_value)}
                  </span>
                )}
              </td>
              <td>
                <span className="tag">{a.origin === 'code' ? 'código' : 'LLM (qualitativa)'}</span>
              </td>
              <td>{a.source_id && <Chips caseId={caseId} ids={[a.source_id]} />}</td>
              <td className="small">{a.justification}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="two-col">
        <Section title="Fatores favoráveis" items={r.favorable_factors} caseId={caseId} />
        <Section title="Fatores de risco" items={r.risk_factors} caseId={caseId} />
      </div>

      <h3>Cenários de stress</h3>
      <table className="table">
        <thead>
          <tr>
            <th>cenário</th>
            <th>choques</th>
            <th>geração de caixa</th>
            <th>cobertura</th>
            <th>classificação</th>
            <th>cálculo</th>
          </tr>
        </thead>
        <tbody>
          {r.stress_scenarios.map((s) => (
            <tr key={s.scenario_id}>
              <td>{s.label}</td>
              <td className="small">
                {Object.entries(s.shocks)
                  .map(([k, v]) => `${k} ${pct(v)}`)
                  .join(' · ') || 'base'}
              </td>
              <td>{brl(s.expected_cash_generation)}</td>
              <td>
                <b>{num(s.coverage, 2)}x</b>
              </td>
              <td>
                <span className={`tag ${s.classification}`}>{CLASSIFICATION_LABEL[s.classification] ?? s.classification}</span>
              </td>
              <td>
                <Chips caseId={caseId} ids={[s.calculation_id]} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="two-col">
        <Section title="Incertezas" items={r.uncertainties} caseId={caseId} />
        <Section title="Dados ausentes" items={r.missing_data} caseId={caseId} />
      </div>

      <h3>Alternativas de estruturação (comparáveis, sem preferência do sistema)</h3>
      <AlternativesGrid caseId={caseId} alternatives={r.alternatives} />

      <h3>
        Findings do Review · {r.review.review_status} · {r.review.open_count} abertos · {r.review.resolved_count} resolvidos
      </h3>
      {r.review.overall_assessment && <p className="small">{r.review.overall_assessment}</p>}
      <Findings caseId={caseId} findings={r.review.findings} />

      <h3>Governança do case</h3>
      <div className="badges">
        <span className="tag ok">escopo: {r.governance.case_scope_client_ids.join(', ')}</span>
        <span className="tag ok">permissões alteradas: {String(r.governance.permissions_changed)}</span>
        <span className="tag">purpose: {r.governance.purpose}</span>
        <span className={`tag ${r.governance.permission_denials ? 'danger' : ''}`}>
          {r.governance.permission_denials} negações
        </span>
        <span className={`tag ${r.governance.security_events ? 'danger' : ''}`}>
          {r.governance.security_events} eventos de segurança
        </span>
        <span className="tag">{r.governance.fields_hidden_total} campos ocultados</span>
      </div>
      <table className="table small">
        <thead>
          <tr>
            <th>agente</th>
            <th>domínios acessados</th>
            <th>tool calls</th>
            <th>negadas</th>
            <th>campos ocultados</th>
            <th>LLM</th>
          </tr>
        </thead>
        <tbody>
          {r.governance.agents.map((a) => (
            <tr key={a.agent_id}>
              <td>{shortAgent(a.agent_id)}</td>
              <td>{a.data_domains_accessed.map((d) => DOMAIN_LABEL[d] ?? d).join(', ') || '—'}</td>
              <td>{a.tool_calls}</td>
              <td>{a.denied_calls}</td>
              <td>{a.fields_hidden}</td>
              <td>{a.fallback_used ? 'fallback' : `${a.llm_calls} chamadas`}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Fontes ({r.sources.length})</h3>
      <ul className="sources">
        {r.sources.map((s) => (
          <li key={s.id}>
            <Chips caseId={caseId} ids={[s.id]} /> <span className="small">{s.label}</span>
            {s.agent_id && <span className="muted small"> · {shortAgent(s.agent_id)}</span>}
            {s.mock && <span className="tag">fictício</span>}
          </li>
        ))}
      </ul>
    </section>
  )
}

function Section({ title, items, caseId }: { title: string; items: ReportItem[]; caseId: string }) {
  return (
    <div>
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="muted small">nenhum item</p>
      ) : (
        <ul className="items">
          {items.map((it, i) => (
            <li key={`${it.code ?? ''}-${i}`}>
              {it.severity && <span className={`tag ${it.severity}`}>{it.severity}</span>} {it.text}{' '}
              <Chips caseId={caseId} ids={it.evidence_ids} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

const ALT_ROWS: Array<[string, (a: Alternative) => React.ReactNode]> = [
  ['Produto', (a) => a.product_id],
  ['Valor', (a) => brl(a.amount)],
  ['Prazo', (a) => `${a.tenor_months} meses`],
  ['Amortização', (a) => a.amortization],
  ['Garantias', (a) => a.guarantees.join(', ')],
  ['Condicionantes', (a) => a.conditions.join(', ') || '—'],
  ['Racional', (a) => a.rationale],
  ['Quando faz sentido', (a) => a.when_it_fits],
  ['Vantagens', (a) => <List items={a.advantages} />],
  ['Riscos', (a) => <List items={a.risks} />],
  ['Trade-offs', (a) => <List items={a.trade_offs} />],
  ['Riscos endereçados', (a) => a.addressed_risk_codes.join(', ') || '—'],
]

function List({ items }: { items: string[] }) {
  return (
    <ul className="plain">
      {items.map((s) => (
        <li key={s}>{s}</li>
      ))}
    </ul>
  )
}

function AlternativesGrid({ caseId, alternatives }: { caseId: string; alternatives: Alternative[] }) {
  return (
    <table className="table alternatives">
      <thead>
        <tr>
          <th></th>
          {alternatives.map((a) => (
            <th key={a.id}>
              {a.id} · {a.name}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {ALT_ROWS.map(([label, render]) => (
          <tr key={label}>
            <th>{label}</th>
            {alternatives.map((a) => (
              <td key={a.id}>{render(a)}</td>
            ))}
          </tr>
        ))}
        <tr>
          <th>Evidências</th>
          {alternatives.map((a) => (
            <td key={a.id}>
              <Chips caseId={caseId} ids={a.evidence_ids} />
            </td>
          ))}
        </tr>
      </tbody>
    </table>
  )
}

export function Findings({ caseId, findings }: { caseId: string; findings: Finding[] }) {
  const sorted = [...findings].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity])
  if (!sorted.length) return <p className="muted small">nenhum finding</p>
  return (
    <ul className="findings">
      {sorted.map((f) => (
        <li key={f.id} className={f.status}>
          <span className={`tag ${f.severity}`}>{f.severity}</span> <code>{f.code}</code>{' '}
          <span className="tag">{f.origin}</span> <span className={`tag status-${f.status}`}>{f.status}</span>
          {f.owner_agent && <span className="muted small"> · owner {shortAgent(f.owner_agent)}</span>}
          {f.required_action && <span className="muted small"> · ação: {f.required_action}</span>}
          <div className="small">{f.message}</div>
          <Chips caseId={caseId} ids={f.evidence_ids} />
        </li>
      ))}
    </ul>
  )
}
