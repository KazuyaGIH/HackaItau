import { ChevronDown } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { keyFigures } from '../answer'
import { DOMAIN_LABEL, ELIGIBILITY_LABEL, REVIEW_STATUS_LABEL, SEVERITY_ORDER, num } from '../format'
import { assumptionName, assumptionValue, coverageText, money, readableItem } from '../humanize'
import { agentName } from '../squad'
import type { CaseState, Finding, Report, ReportItem } from '../types'
import { CoverageChart } from './CoverageChart'
import { REPORT_SECTIONS } from '../panel'
import { OptionCards } from './Options'
import { SourceChip, Sources } from './SourceChip'

const NOT_APPROVAL = 'Não representa aprovação de crédito'
const SEVERITY_LABEL: Record<string, string> = { high: 'alta', medium: 'média', low: 'baixa', info: 'informativo' }
const FINDING_STATUS: Record<string, string> = { open: 'aberto', resolved: 'resolvido', informational: 'informativo' }

// Relatório consolidado como um documento: primeiro o que decidir, depois o porquê, os detalhes técnicos no fim.
export function ReportView({ report, state, section }: { report: Report; state: CaseState | null; section?: string }) {
  const r = report
  useEffect(() => {
    if (section) document.getElementById(section)?.scrollIntoView({ block: 'start' })
  }, [section])
  const base = r.stress_scenarios.find((s) => Object.keys(s.shocks).length === 0)
  const stressed = r.stress_scenarios.filter((s) => Object.keys(s.shocks).length > 0)
  const weak = stressed.filter((s) => s.classification === 'insufficient' || s.classification === 'attention_required')
  const it = state?.interpreted
  const title = [r.summary.purpose ?? 'Crédito', r.summary.crop && `de ${r.summary.crop}`, it?.cycle].filter(Boolean).join(' ')

  return (
    <article className="doc">
      <p className="doc-disclaimer">
        {r.disclaimer.includes(NOT_APPROVAL)
          ? r.disclaimer
          : `Análise gerada para suporte à decisão. ${NOT_APPROVAL}. ${r.disclaimer}`}
      </p>

      <header className="doc-head">
        <h2>
          {title.charAt(0).toUpperCase() + title.slice(1)}, {it?.client_ref ?? r.client_id}
        </h2>
        <p className="doc-lede">
          {money(r.summary.requested_amount ?? 0)} solicitados. A Elegibilidade concluiu{' '}
          <strong>{ELIGIBILITY_LABEL[r.summary.eligibility_status] ?? r.summary.eligibility_status}</strong>.
          {base &&
            ` No cenário base, a geração de caixa cobre ${coverageText(base.coverage)} o valor pedido`}
          {base && r.policy_limits?.coverage_comfortable_min
            ? `, ${base.coverage >= r.policy_limits.coverage_comfortable_min ? 'acima' : 'abaixo'} do nível confortável da política (${coverageText(r.policy_limits.coverage_comfortable_min)})`
            : ''}
          {base && '.'}
          {stressed.length > 0 &&
            (weak.length
              ? ` Em ${weak.length} de ${stressed.length} cenários de estresse a cobertura fica abaixo do exigido.`
              : ' Nos cenários de estresse a cobertura se mantém dentro da política.')}{' '}
          A squad propôs {r.alternatives.length} opções de estrutura, sem preferência do sistema.
        </p>
        <div className="doc-figures">
          {keyFigures(r).map((f) => (
            <div key={f.label} className={`figure ${f.tone}`}>
              <span className="figure-label">{f.label}</span>
              <span className="figure-value">{f.value}</span>
              <span className="figure-note">{f.note}</span>
            </div>
          ))}
        </div>
      </header>

      <Section id={REPORT_SECTIONS.capacity} title="Capacidade de pagamento" origin="code">
        <CoverageChart report={r} />
      </Section>

      <Section id={REPORT_SECTIONS.options} title="Opções de estrutura">
        <p className="doc-note">
          Mesmos campos, na mesma ordem, para comparar. A escolha é do analista; o sistema não ranqueia as opções.
        </p>
        <OptionCards alternatives={r.alternatives} />
      </Section>

      <Section title="Riscos e pontos a favor" origin="llm">
        <ItemList title="Riscos" items={r.risk_factors} withSeverity />
        <ItemList title="Pontos a favor" items={r.favorable_factors} />
      </Section>

      <Section title="Premissas usadas nos cálculos" origin="code">
        <table className="table plain-table">
          <tbody>
            {r.assumptions
              .filter((a) => a.origin === 'code')
              .map((a) => (
                <tr key={a.name} className={a.changed_in_rework ? 'changed' : ''}>
                  <th>{assumptionName(a.name)}</th>
                  <td>
                    {assumptionValue(a.value, a.unit)}
                    {a.changed_in_rework && (
                      <span className="was">
                        corrigida pela revisão; antes {assumptionValue(a.previous_value, a.unit)}
                      </span>
                    )}
                  </td>
                  <td className="small">{a.source_id && <SourceChip id={a.source_id} label="fonte" />}</td>
                </tr>
              ))}
          </tbody>
        </table>
        {r.assumptions.some((a) => a.origin !== 'code') && (
          <ItemList
            title="Observações qualitativas do modelo (não entram nas contas)"
            items={r.assumptions
              .filter((a) => a.origin !== 'code')
              .map((a) => ({ text: String(a.value), evidence_ids: [], severity: null, code: a.name }))}
          />
        )}
      </Section>

      <Section title={`Pendências e incertezas (${r.missing_data.length + r.uncertainties.length})`}>
        {r.missing_data.length + r.uncertainties.length === 0 ? (
          <p className="doc-note">Nenhuma registrada.</p>
        ) : (
          <>
            <ItemList title="Dados que faltam" items={r.missing_data} hideEmpty />
            <ItemList title="Incertezas" items={r.uncertainties} hideEmpty />
          </>
        )}
      </Section>

      <Section title="O que a revisão encontrou">
        <p className="doc-note">
          {capitalize(REVIEW_STATUS_LABEL[r.review.review_status] ?? r.review.review_status)}, com{' '}
          {r.review.resolved_count} achado(s) resolvido(s) pelo retrabalho e {r.review.open_count} em aberto.
          {r.review.overall_assessment && ` ${r.review.overall_assessment}`}
        </p>
        <Findings findings={r.review.findings} />
      </Section>

      <div className="doc-details">
        <Fold title={`Fórmulas e entradas dos cálculos (${r.calculations.length})`}>
          <div className="calcs">
            {r.calculations.map((c) => (
              <div key={c.calculation_id} className="calc">
                <div className="calc-head">
                  <SourceChip id={c.calculation_id} />
                </div>
                <pre className="formula">{c.formula}</pre>
                <table className="kv">
                  <tbody>
                    {Object.entries(c.outputs)
                      .filter(([, v]) => typeof v !== 'object' || v === null)
                      .map(([k, v]) => (
                        <tr key={k}>
                          <td>{k.replace(/_/g, ' ')}</td>
                          <td className="num">{num(v, 4)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        </Fold>
        <Fold title="Contribuição da squad">
          <SquadContribution report={r} state={state} />
        </Fold>
        <Fold title={`Todas as fontes (${r.sources.length})`}>
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
      </div>
    </article>
  )
}

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

function Section({
  id,
  title,
  origin,
  children,
}: {
  id?: string
  title: string
  origin?: 'code' | 'llm'
  children: ReactNode
}) {
  return (
    <section className="doc-section" id={id}>
      <h3>
        {title}
        {origin === 'code' && <span className="origin code">calculado por código</span>}
        {origin === 'llm' && <span className="origin llm">escrito pelo modelo, com fontes</span>}
      </h3>
      {children}
    </section>
  )
}

function Fold({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="fold">
      <summary>
        <ChevronDown size={16} className="chev" />
        <span>{title}</span>
      </summary>
      <div className="fold-body">{children}</div>
    </details>
  )
}

function ItemList({
  title,
  items,
  withSeverity,
  hideEmpty,
}: {
  title: string
  items: ReportItem[]
  withSeverity?: boolean
  hideEmpty?: boolean
}) {
  if (!items.length && hideEmpty) return null
  const sorted = withSeverity
    ? [...items].sort((a, b) => SEVERITY_ORDER[a.severity ?? 'info'] - SEVERITY_ORDER[b.severity ?? 'info'])
    : items
  return (
    <div className="item-list">
      <h4>{title}</h4>
      {items.length === 0 ? (
        <p className="doc-note">Nenhum.</p>
      ) : (
        <ul>
          {sorted.map((it, i) => (
            <li key={`${it.code ?? ''}-${i}`}>
              {withSeverity && it.severity && <span className={`tag ${it.severity}`}>{SEVERITY_LABEL[it.severity]}</span>}
              <span>{readableItem(it.text)}</span>
              <Sources ids={it.evidence_ids} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Findings({ findings }: { findings: Finding[] }) {
  const sorted = [...findings].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity])
  if (!sorted.length) return null
  return (
    <ul className="findings">
      {sorted.map((f) => (
        <li key={f.id} className={f.status}>
          <div className="finding-head">
            <span className={`tag ${f.severity}`}>{SEVERITY_LABEL[f.severity]}</span>
            {f.status !== 'informational' && (
              <span className={`tag status-${f.status}`}>{FINDING_STATUS[f.status] ?? f.status}</span>
            )}
            {f.owner_agent && <span className="muted small">responsável: {agentName(f.owner_agent)}</span>}
          </div>
          <p>{f.message.replace(/`/g, '')}</p>
          <Sources ids={f.evidence_ids} />
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
          <th>Dados que leu</th>
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
