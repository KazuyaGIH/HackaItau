import { CircleMinus, CirclePlus, Scale } from 'lucide-react'
import { money, term, terms } from '../humanize'
import type { Alternative } from '../types'
import { Sources } from './SourceChip'

// Estruturas de crédito como opções comparáveis: mesmos campos na mesma ordem, numeradas, sem preferência do sistema.
export function OptionCards({
  alternatives,
  compact = false,
  onOpen,
}: {
  alternatives: Alternative[]
  compact?: boolean
  onOpen?: () => void
}) {
  return (
    <div className={`options${compact ? ' compact' : ''}`}>
      {alternatives.map((a, i) =>
        compact ? (
          <button key={a.id} type="button" className="option" onClick={onOpen}>
            <span className="option-index">Opção {i + 1}</span>
            <strong className="option-name">{a.name}</strong>
            <span className="option-line">
              {money(a.amount)} em {a.tenor_months} meses
            </span>
            <span className="option-line">{term(a.amortization)}</span>
            <span className="option-line muted">Garantias: {terms(a.guarantees)}</span>
          </button>
        ) : (
          <article key={a.id} className="option">
            <span className="option-index">Opção {i + 1}</span>
            <h4 className="option-name">{a.name}</h4>
            <dl className="option-facts">
              <div>
                <dt>Valor</dt>
                <dd>{money(a.amount)}</dd>
              </div>
              <div>
                <dt>Prazo</dt>
                <dd>{a.tenor_months} meses</dd>
              </div>
              <div>
                <dt>Pagamento</dt>
                <dd>{term(a.amortization)}</dd>
              </div>
              <div>
                <dt>Garantias</dt>
                <dd>{terms(a.guarantees)}</dd>
              </div>
              <div>
                <dt>Condicionantes</dt>
                <dd>{a.conditions.length ? terms(a.conditions) : 'nenhuma'}</dd>
              </div>
            </dl>
            {a.when_it_fits && (
              <p className="option-when">
                <strong>Quando faz sentido:</strong> {a.when_it_fits}
              </p>
            )}
            <ul className="option-points">
              {a.advantages.map((t) => (
                <li key={`a-${t}`} className="pro">
                  <CirclePlus size={14} />
                  {t}
                </li>
              ))}
              {a.risks.map((t) => (
                <li key={`r-${t}`} className="con">
                  <CircleMinus size={14} />
                  {t}
                </li>
              ))}
              {a.trade_offs.map((t) => (
                <li key={`t-${t}`} className="trade">
                  <Scale size={14} />
                  {t}
                </li>
              ))}
            </ul>
            {a.addressed_risk_codes.length > 0 && (
              <p className="small muted">Responde a: {terms(a.addressed_risk_codes)}.</p>
            )}
            <Sources ids={a.evidence_ids} />
          </article>
        ),
      )}
    </div>
  )
}
