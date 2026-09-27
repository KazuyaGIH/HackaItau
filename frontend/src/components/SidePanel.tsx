import { ArrowLeft, X } from 'lucide-react'
import type { PanelView } from '../panel'
import type { CaseEvent, CaseState, Report } from '../types'
import { GovernancePanel, Timeline } from './Governance'
import { ReportView } from './ReportView'
import { EvidenceView } from './SourceChip'

interface Props {
  view: PanelView
  caseId: string
  state: CaseState | null
  events: CaseEvent[]
  reports: Record<number, Report>
  onNavigate: (view: PanelView) => void
  onClose: () => void
}

export function SidePanel({ view, caseId, state, events, reports, onNavigate, onClose }: Props) {
  const versions = Object.keys(reports)
    .map(Number)
    .sort((a, b) => a - b)

  let title = 'Auditoria e governança'
  let body = state ? (
    <>
      <GovernancePanel state={state} events={events} />
      <Timeline events={events} />
    </>
  ) : null
  let back: PanelView | null = null

  if (view.kind === 'report') {
    const seq = view.reportSeq ?? versions[versions.length - 1] ?? null
    const report = (seq !== null ? reports[seq] : null) ?? state?.report ?? null
    title = 'Relatório para revisão humana'
    body = report ? <ReportView report={report} state={state} /> : <p className="muted">O relatório ainda não foi consolidado.</p>
    if (versions.length > 1) {
      const current = seq ?? versions[versions.length - 1]
      body = (
        <>
          <div className="versions" role="tablist" aria-label="Versões do relatório">
            {versions.map((v, i) => (
              <button
                key={v}
                type="button"
                role="tab"
                aria-selected={v === current}
                className={v === current ? 'on' : ''}
                onClick={() => onNavigate({ kind: 'report', reportSeq: v })}
              >
                Versão {i + 1}
                {i === 0 ? ', original' : ', com ajuste'}
              </button>
            ))}
          </div>
          {body}
        </>
      )
    }
  } else if (view.kind === 'evidence') {
    title = 'Evidência'
    back = view.back
    body = (
      <>
        <p className="evidence-id">{view.id}</p>
        <EvidenceView key={view.id} caseId={caseId} id={view.id} />
      </>
    )
  }

  return (
    <aside className="side-panel" aria-label={title}>
      <header className="panel-head">
        {back && (
          <button type="button" className="icon-btn" onClick={() => onNavigate(back!)} aria-label="Voltar" title="Voltar">
            <ArrowLeft size={18} />
          </button>
        )}
        <h2>{title}</h2>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Fechar painel" title="Fechar painel">
          <X size={18} />
        </button>
      </header>
      <div className="panel-body">{body}</div>
    </aside>
  )
}
