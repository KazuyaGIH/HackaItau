import { CLASSIFICATION_LABEL } from '../format'
import { coverageText } from '../humanize'
import type { Report } from '../types'

// Cobertura (geração de caixa ÷ valor pedido) por cenário, com os limites da política como referência.
// Uma série só (cor de destaque), valor escrito na ponta de cada barra, classificação em texto ao lado.
export function CoverageChart({ report }: { report: Report }) {
  const scenarios = report.stress_scenarios
  const limits = report.policy_limits
  const refs = [
    { v: limits?.coverage_attention_required_min, label: 'mínimo' },
    { v: limits?.coverage_comfortable_min, label: 'confortável' },
  ].filter((r): r is { v: number; label: string } => typeof r.v === 'number')
  const values = scenarios.map((s) => s.coverage)
  const lo = Math.min(0, ...values)
  const hi = Math.max(1.6, ...values, ...refs.map((r) => r.v)) * 1.08
  const pos = (v: number) => ((v - lo) / (hi - lo)) * 100

  return (
    <figure className="cov" aria-label="Cobertura por cenário">
      <div className="cov-row cov-head" aria-hidden="true">
        <span />
        <span className="cov-track">
          {refs.map((r) => (
            <span key={r.label} className="cov-ref-label" style={{ left: `${pos(r.v)}%` }}>
              {coverageText(r.v)}
            </span>
          ))}
        </span>
      </div>
      {scenarios.map((s) => {
        const left = pos(Math.min(0, s.coverage))
        const width = Math.max(0.6, Math.abs(pos(s.coverage) - pos(0)))
        const tip = pos(Math.max(0, s.coverage))
        return (
          <div className="cov-row" key={s.scenario_id} title={`${s.label}: cobertura de ${coverageText(s.coverage)}`}>
            <span className="cov-label">
              {s.label}
              <span className={`tag ${s.classification}`}>{CLASSIFICATION_LABEL[s.classification] ?? s.classification}</span>
            </span>
            <span className="cov-track">
              {refs.map((r) => (
                <span key={r.label} className="cov-ref" style={{ left: `${pos(r.v)}%` }} />
              ))}
              <span className="cov-zero" style={{ left: `${pos(0)}%` }} />
              <span className={`cov-bar${s.coverage < 0 ? ' negative' : ''}`} style={{ left: `${left}%`, width: `${width}%` }} />
              <span className="cov-value" style={{ left: `calc(${tip}% + 6px)` }}>
                {coverageText(s.coverage)}
              </span>
            </span>
          </div>
        )
      })}
      <figcaption className="small muted">
        Cobertura = geração de caixa esperada ÷ valor pedido, calculada por código. Linhas verticais: limites da política
        {limits?.source_doc_id ? ` ${limits.source_doc_id}` : ''}
        {refs.length ? ` (${refs.map((r) => `${coverageText(r.v)} ${r.label}`).join(', ')})` : ''}.
      </figcaption>
    </figure>
  )
}
