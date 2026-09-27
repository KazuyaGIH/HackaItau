// Painel lateral (à direita, como um "artifact"): relatório, auditoria ou uma evidência específica.
import { createContext, useContext } from 'react'

export type PanelView =
  | { kind: 'report'; reportSeq: number | null }
  | { kind: 'audit' }
  | { kind: 'evidence'; id: string; back: PanelView | null }

export interface PanelApi {
  caseId: string | null
  view: PanelView | null
  open: (view: PanelView) => void
  openEvidence: (id: string) => void
  close: () => void
}

export const PanelContext = createContext<PanelApi>({
  caseId: null,
  view: null,
  open: () => {},
  openEvidence: () => {},
  close: () => {},
})

export const usePanel = () => useContext(PanelContext)
