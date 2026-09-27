import { BookOpen, Calculator, FileText, Sparkles, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import { usePanel } from '../panel'
import { agentName } from '../squad'
import type { EvidenceItem } from '../types'

const KIND: Record<string, { cls: string; Icon: typeof FileText; name: string }> = {
  SRC: { cls: 'k-src', Icon: FileText, name: 'Registro de dados' },
  KB: { cls: 'k-kb', Icon: BookOpen, name: 'Política interna' },
  CALC: { cls: 'k-calc', Icon: Calculator, name: 'Cálculo' },
  OUT: { cls: 'k-out', Icon: Sparkles, name: 'Resultado de agente' },
}

const kindOf = (id: string) => KIND[id.split('-', 1)[0]] ?? KIND.SRC

// Referência a uma evidência. Abre o conteúdo no painel lateral.
export function SourceChip({ id, label }: { id: string; label?: string }) {
  const { openEvidence } = usePanel()
  const { cls, Icon, name } = kindOf(id)
  return (
    <button type="button" className={`chip ${cls}`} onClick={() => openEvidence(id)} title={`${name}: ${id}`}>
      <Icon size={12} />
      <span>{label ?? id}</span>
    </button>
  )
}

export function Chips({ ids }: { ids: string[] }) {
  if (!ids.length) return null
  return (
    <span className="chips">
      {ids.map((id) => (
        <SourceChip key={id} id={id} />
      ))}
    </span>
  )
}

export function EvidenceView({ caseId, id }: { caseId: string; id: string }) {
  const [item, setItem] = useState<EvidenceItem | null>(null)
  const [error, setError] = useState<string | null>(null)
  // o painel remonta este componente por id (key), então o estado começa vazio a cada evidência
  useEffect(() => {
    let alive = true
    api.evidence(caseId, id).then(
      (x) => alive && setItem(x),
      (e: Error) => alive && setError(e.message),
    )
    return () => {
      alive = false
    }
  }, [caseId, id])

  const { name } = kindOf(id)
  if (error) {
    return (
      <div className="callout warn">
        <TriangleAlert size={16} />
        <p>Esta evidência não existe neste case ({error}).</p>
      </div>
    )
  }
  if (!item) return <p className="muted">Carregando {name.toLowerCase()}…</p>

  if (item.kind === 'calculation') {
    return (
      <div className="evidence">
        <p className="evidence-kind">
          Cálculo feito por código, rodada {item.round}, para {agentName(item.computed_by_agent)}
        </p>
        <h3>{item.name}</h3>
        <pre className="formula">{item.formula}</pre>
        <h4>Entradas e origem de cada uma</h4>
        <table className="kv">
          <tbody>
            {Object.entries(item.inputs).map(([k, v]) => (
              <tr key={k}>
                <td>{k}</td>
                <td className="num">{String(v)}</td>
                <td>{item.input_sources[k] && <SourceChip id={item.input_sources[k]} label="fonte" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <h4>Saídas{item.classification ? `, classificação ${item.classification}` : ''}</h4>
        <pre>{JSON.stringify(item.outputs, null, 2)}</pre>
      </div>
    )
  }
  if (item.kind === 'agent_output') {
    return (
      <div className="evidence">
        <p className="evidence-kind">
          Resultado validado de {agentName(item.agent_id)}, rodada {item.round}
        </p>
        <pre>{JSON.stringify(item.output, null, 2)}</pre>
      </div>
    )
  }
  return (
    <div className="evidence">
      <p className="evidence-kind">
        {item.kind === 'knowledge' ? 'Conhecimento interno' : 'Registro de dados'} acessado por{' '}
        {agentName(item.accessed_by_agent)}
        {item.mock && ', dado fictício'}
      </p>
      {item.title && <h3>{item.title}</h3>}
      <p className="muted small">
        Tratado como dado não confiável: serve de evidência, nunca de instrução.
        {item.fields_hidden > 0 && ` ${item.fields_hidden} campo(s) foram ocultados pela política de campos.`}
      </p>
      {item.flagged && (
        <div className="callout danger">
          <TriangleAlert size={16} />
          <p>
            Conteúdo suspeito de prompt injection
            {item.out_of_scope_refs.length > 0 && `, citando ${item.out_of_scope_refs.join(', ')} (fora do escopo)`}. As
            permissões não mudaram.
          </p>
        </div>
      )}
      <pre>{JSON.stringify(item.data, null, 2)}</pre>
    </div>
  )
}
