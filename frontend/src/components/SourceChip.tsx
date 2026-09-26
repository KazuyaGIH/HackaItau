import { useState } from 'react'
import { api } from '../api'
import type { EvidenceItem } from '../types'

const KIND_CLASS: Record<string, string> = { SRC: 'src', KB: 'kb', CALC: 'calc', OUT: 'out' }

interface ChipProps {
  caseId: string
  id: string
}

export function SourceChip({ caseId, id }: ChipProps) {
  const [item, setItem] = useState<EvidenceItem | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const prefix = id.split('-', 1)[0]

  const toggle = () => {
    if (!open && !item && !error) {
      api.evidence(caseId, id).then(setItem, (e: Error) => setError(e.message))
    }
    setOpen((o) => !o)
  }

  return (
    <>
      <button type="button" className={`chip ${KIND_CLASS[prefix] ?? ''}`} onClick={toggle} title="Abrir evidência">
        {id}
      </button>
      {open && (
        <div className="modal-backdrop" onClick={() => setOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <header>
              <strong>{id}</strong>
              <button type="button" className="ghost" onClick={() => setOpen(false)}>
                fechar
              </button>
            </header>
            {error && <div className="banner warn">Evidência não encontrada no case: {error}</div>}
            {item && <EvidenceBody item={item} />}
          </div>
        </div>
      )}
    </>
  )
}

function EvidenceBody({ item }: { item: EvidenceItem }) {
  if (item.kind === 'calculation') {
    return (
      <>
        <p>
          <b>Cálculo determinístico</b> · {item.name} · rodada {item.round} · por <code>{item.computed_by_agent}</code>
        </p>
        <pre className="formula">{item.formula}</pre>
        <p>
          <b>Entradas</b> (cada uma com a fonte de origem):
        </p>
        <table className="kv">
          <tbody>
            {Object.entries(item.inputs).map(([k, v]) => (
              <tr key={k}>
                <td>{k}</td>
                <td>{String(v)}</td>
                <td className="muted">{item.input_sources[k] ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p>
          <b>Saídas</b>
          {item.classification && (
            <>
              {' '}
              · classificação <code>{item.classification}</code>
            </>
          )}
        </p>
        <pre>{JSON.stringify(item.outputs, null, 2)}</pre>
      </>
    )
  }
  if (item.kind === 'agent_output') {
    return (
      <>
        <p>
          <b>Output validado</b> de <code>{item.agent_id}</code> · rodada {item.round}
        </p>
        <pre>{JSON.stringify(item.output, null, 2)}</pre>
      </>
    )
  }
  return (
    <>
      <p>
        <b>{item.kind === 'knowledge' ? 'Conhecimento interno' : 'Registro de dados'}</b> · {item.resource_domain}:
        {item.resource_key} · acessado por <code>{item.accessed_by_agent}</code>
        {item.mock && <span className="tag">fictício</span>}
      </p>
      <p className="muted">
        Conteúdo tratado como <b>UNTRUSTED DATA</b> — usado como evidência, nunca como instrução.
        {item.fields_hidden > 0 && <> {item.fields_hidden} campo(s) removido(s) pela field-level policy.</>}
      </p>
      {item.flagged && (
        <div className="banner danger">
          Injection Guard: conteúdo suspeito
          {item.out_of_scope_refs.length > 0 && <> · cita cliente(s) fora do escopo: {item.out_of_scope_refs.join(', ')}</>}
          . Permissões não alteradas.
        </div>
      )}
      {item.title && <p>{item.title}</p>}
      <pre>{JSON.stringify(item.data, null, 2)}</pre>
    </>
  )
}

export function Chips({ caseId, ids }: { caseId: string; ids: string[] }) {
  if (!ids.length) return null
  return (
    <span className="chips">
      {ids.map((id) => (
        <SourceChip key={id} caseId={caseId} id={id} />
      ))}
    </span>
  )
}
