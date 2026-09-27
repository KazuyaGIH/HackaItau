import { ChevronDown } from 'lucide-react'
import type { ReactNode } from 'react'
import {
  CLASSIFICATION_LABEL,
  DOMAIN_LABEL,
  ELIGIBILITY_LABEL,
  REVIEW_STATUS_LABEL,
  SEVERITY_ORDER,
  brl,
  num,
  pct,
} from '../format'
import { agentName } from '../squad'
import type { Alternative, CaseState, Finding, Report, ReportItem } from '../types'
import { Chips, SourceChip } from './SourceChip'

const NOT_APPROVAL = 'Não representa aprovação de crédito'

const SEVERITY_LABEL: Record<string, string> = { high: 'alta', medium: 'média', low: 'baixa', info: 'informativo' }
const FINDING_STATUS: Record<string, string> = { open: 'aberto', resolved: 'resolvido', informational: 'informativo' }

// Relatório consolidado, exibido no painel lateral. Números vêm de cálculos por código; textos do modelo citam evidências.
export function ReportView({ report, state }: { report: Report; state: CaseState | null }) {
  const r = report
  return (
    <article className="report">
      <p className="report-disclaimer">
        {r.disclaimer.includes(NOT_APPROVAL)
          ? r.disclaimer
          : `Análise gerada para suporte à decisão. ${NOT_APPROVAL}. ${r.disclaimer}`}
      </p>

      <dl className="report-summary">
        <div>
          <dt>Cliente</dt>
          <dd>{r.client_id}</dd>
        </div>
        <div>
          <dt>Valor solicitado</dt>
          <dd className="num">{brl(r.summary.requested_amount)}</dd>
        </div>
        <div>
          <dt>Finalidade</dt>
          <dd>
            {r.summary.purpose ?? '—'}, {r.summary.crop ?? '—'}
          </dd>
        </div>
        <div>
          <dt>Elegibilidade</dt>
          <dd>{ELIGIBILITY_LABEL[r.summary.eligibility_status] ?? r.summary.eligibility_status}</dd>
        </div>
        <div>
          <dt>Alternativas</dt>
          <dd className="num">{r.summary.alternatives_count}</dd>
        </div>
        <div>
          <dt>Retrabalho</dt>
          <dd className="num">{r.summary.rework_rounds}</dd>
        </div>
      </dl>

      <Fold title="Capacidade de pagamento e estresse" origin="code" open>
        <StressTable report={r} />
        <Fold title={`Fórmulas e entradas (${r.calculations.length} cálculos)`} inner>
          <div className="calcs">
            {r.calculations.map((c) => (
              <div key={c.calculation_id} className="calc">
                <div className="calc-head">
                  <SourceChip id={c.calculation_id} />
                  <strong>{c.name}</strong>
                  {c.classification && <span className="tag">{CLASSIFICATION_LABEL[c.classification] ?? c.classification}</span>}
                </div>
                <pre className="formula">{c.formula}</pre>
                <table className="kv">
                  <tbody>
                    {Object.entries(c.outputs)
                      .filter(([, v]) => typeof v !== 'object' || v === null)
                      .map(([k, v]) => (
                        <tr key={k}>
                          <td>{k}</td>
                          <td className="num">{num(v, 4)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
                <p className="muted small">
                  Limites da política: <Chips ids={c.thresholds_source_ids} />
                </p>
              </div>
            ))}
          </div>
        </Fold>
      </Fold>

      <Fold title="Riscos e fatores favoráveis" origin="llm" open>
        <Items title="Fatores de risco" items={r.risk_factors} />
        <Items title="Fatores favoráveis" items={r.favorable_factors} />
      </Fold>

      <Fold title="Estruturas alternativas" open>
        <p className="muted small">Comparáveis, sem preferência do sistema. A escolha é do analista.</p>
        <AlternativesTable alternatives={r.alternatives} />
      </Fold>

      <Fold title={`Pendências e incertezas (${r.missing_data.length + r.uncertainties.length})`}>
        <Items title="Dados ausentes" items={r.missing_data} />
        <Items title="Incertezas" items={r.uncertainties} />
      </Fold>

      <Fold title="Fatos e premissas">
        <Items title="Fatos" items={r.facts} />
        <h4>Premissas</h4>
        <table className="table">
          <thead>
            <tr>
              <th>Premissa</th>
              <th>Valor</th>
              <th>Origem</th>
              <th>Justificativa</th>
            </tr>
          </thead>
          <tbody>
            {r.assumptions.map((a) => (
              <tr key={a.name} className={a.changed_in_rework ? 'changed' : ''}>
                <td>
                  {a.name} {a.source_id && <SourceChip id={a.source_id} label="fonte" />}
                </td>
                <td className="num">
                  {num(a.value)} {a.unit ?? ''}
                  {a.changed_in_rework && <span className="was">antes {num(a.previous_value)}</span>}
                </td>
                <td>{a.origin === 'code' ? 'código' : 'modelo (qualitativa)'}</td>
                <td className="small">{a.justification}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Fold>

      <Fold
        title={`Revisão: ${REVIEW_STATUS_LABEL[r.review.review_status] ?? r.review.review_status}, ${r.review.open_count} aberto(s), ${r.review.resolved_count} resolvido(s)`}
      >
        {r.review.overall_assessment && <p className="small">{r.review.overall_assessment}</p>}
        <Findings findings={r.review.findings} />
      </Fold>

      <Fold title="Contribuição da squad">
        <SquadContribution report={r} state={state} />
      </Fold>

      <Fold title={`Fontes (${r.sources.length})`}>
        <ul className="sources">
          {r.sources.map((s) => (
            <li key={s.id}>
              <SourceChip id={s.id} />
              <span className="small">{s.label}</span>
              {s.agent_id && <span className="muted small">{agentName(s.agent_id)}</span>}
            </li>
          ))}
        </ul>
      </Fold>
    </article>
  )
}

function Fold({
  title,
  origin,
  open,
  inner,
  children,
}: {
  title: string
  origin?: 'code' | 'llm'
  open?: boolean
  inner?: boolean
  children: ReactNode
}) {
  return (
    <details className={`fold${inner ? ' inner' : ''}`} open={open}>
      <summary>
        <ChevronDown size={16} className="chev" />
        <span>{title}</span>
        {origin === 'code' && <span className="origin code">calculado por código</span>}
        {origin === 'llm' && <span className="origin llm">texto do modelo, com evidências</span>}
      </summary>
      <div className="fold-body">{children}</div>
    </details>
  )
}

function StressTable({ report }: { report: Report }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Cenário</th>
          <th>Geração de caixa</th>
          <th>Cobertura</th>
          <th>Classificação</th>
        </tr>
      </thead>
      <tbody>
        {report.stress_scenarios.map((s) => (
          <tr key={s.scenario_id}>
            <td>
              {s.label}
              <div className="muted small">
                {Object.entries(s.shocks)
                  .map(([k, v]) => `${k} ${pct(v)}`)
                  .join(', ') || 'sem choque'}
              </div>
            </td>
            <td className="num">{brl(s.expected_cash_generation)}</td>
            <td className="num strong">{num(s.coverage, 2)}x</td>
            <td>
              <span className={`tag ${s.classification}`}>{CLASSIFICATION_LABEL[s.classification] ?? s.classification}</span>
              <SourceChip id={s.calculation_id} label="cálculo" />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Items({ title, items }: { title: string; items: ReportItem[] }) {
  return (
    <>
      <h4>{title}</h4>
      {items.length === 0 ? (
        <p className="muted small">Nenhum item.</p>
      ) : (
        <ul className="items">
          {items.map((it, i) => (
            <li key={`${it.code ?? ''}-${i}`}>
              {it.severity && <span className={`tag ${it.severity}`}>{SEVERITY_LABEL[it.severity]}</span>} {it.text}{' '}
              <Chips ids={it.evidence_ids} />
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

const ALT_ROWS: Array<[string, (a: Alternative) => ReactNode]> = [
  ['Produto', (a) => a.product_id],
  ['Valor', (a) => brl(a.amount)],
  ['Prazo', (a) => `${a.tenor_months} meses`],
  ['Amortização', (a) => a.amortization],
  ['Garantias', (a) => a.guarantees.join(', ')],
  ['Condicionantes', (a) => a.conditions.join(', ') || '—'],
  ['Racional', (a) => a.rationale],
  ['Quando faz sentido', (a) => a.when_it_fits],
  ['Vantagens', (a) => <Plain items={a.advantages} />],
  ['Riscos', (a) => <Plain items={a.risks} />],
  ['Trade-offs', (a) => <Plain items={a.trade_offs} />],
  ['Evidências', (a) => <Chips ids={a.evidence_ids} />],
]

function Plain({ items }: { items: string[] }) {
  return (
    <ul className="plain">
      {items.map((s) => (
        <li key={s}>{s}</li>
      ))}
    </ul>
  )
}

function AlternativesTable({ alternatives }: { alternatives: Alternative[] }) {
  return (
    <div className="table-scroll">
      <table className="table alternatives">
        <thead>
          <tr>
            <th />
            {alternatives.map((a) => (
              <th key={a.id}>{a.name}</th>
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
        </tbody>
      </table>
    </div>
  )
}

function Findings({ findings }: { findings: Finding[] }) {
  const sorted = [...findings].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity])
  if (!sorted.length) return <p className="muted small">Nenhum achado.</p>
  return (
    <ul className="findings">
      {sorted.map((f) => (
        <li key={f.id} className={f.status}>
          <div className="finding-head">
            <span className={`tag ${f.severity}`}>{SEVERITY_LABEL[f.severity]}</span>
            <span className={`tag status-${f.status}`}>{FINDING_STATUS[f.status] ?? f.status}</span>
            {f.owner_agent && <span className="muted small">responsável: {agentName(f.owner_agent)}</span>}
          </div>
          <p className="small">{f.message}</p>
          <Chips ids={f.evidence_ids} />
        </li>
      ))}
    </ul>
  )
}

function SquadContribution({ report, state }: { report: Report; state: CaseState | null }) {
  const gov = new Map(report.governance.agents.map((a) => [a.agent_id, a]))
  const owned = (id: string) => report.review.findings.filter((f) => f.owner_agent === id).length
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Agente</th>
          <th>Rodadas</th>
          <th>Acessos</th>
          <th>Negados</th>
          <th>Domínios</th>
          <th>Achados</th>
        </tr>
      </thead>
      <tbody>
        {(state?.agents ?? []).map((a) => (
          <tr key={a.agent_id}>
            <td>{agentName(a.agent_id)}</td>
            <td className="num">{a.round}</td>
            <td className="num">{gov.get(a.agent_id)?.tool_calls ?? a.tool_calls}</td>
            <td className={`num${a.denied_calls ? ' danger-text' : ''}`}>{a.denied_calls}</td>
            <td className="small">{a.data_domains_accessed.map((d) => DOMAIN_LABEL[d] ?? d).join(', ') || '—'}</td>
            <td className="num">{owned(a.agent_id)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
