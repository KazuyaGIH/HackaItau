import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { Conversation } from './components/Conversation'
import { PerformanceView } from './components/PerformanceView'
import { SidePanel } from './components/SidePanel'
import { Sidebar } from './components/Sidebar'
import { PanelContext, type PanelApi, type PanelView } from './panel'
import { useWorkspace } from './workspace'

const narrow = () => typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches

export default function App() {
  const ws = useWorkspace()
  const [llmReady, setLlmReady] = useState<boolean | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(() => !narrow())
  const [panel, setPanel] = useState<PanelView | null>(null)
  const [view, setView] = useState<'chat' | 'performance'>('chat')

  useEffect(() => {
    api.health().then(
      (h) => setLlmReady(h.llm_mode === 'real'),
      () => setLlmReady(null),
    )
  }, [])

  const caseId = ws.branch?.caseId ?? null
  // o painel pertence ao case aberto: trocar de conversa ou de versão fecha o painel
  const [panelCase, setPanelCase] = useState<string | null>(caseId)
  if (panelCase !== caseId) {
    setPanelCase(caseId)
    setPanel(null)
  }

  const panelApi = useMemo<PanelApi>(
    () => ({
      caseId,
      view: panel,
      open: setPanel,
      openEvidence: (id) => setPanel((v) => ({ kind: 'evidence', id, back: v?.kind === 'evidence' ? v.back : v })),
      close: () => setPanel(null),
    }),
    [caseId, panel],
  )

  const openConversation = (id: string) => {
    ws.openConversation(id)
    setView('chat')
    if (narrow()) setSidebarOpen(false)
  }

  return (
    <PanelContext.Provider value={panelApi}>
      <div className={`app${sidebarOpen ? ' with-sidebar' : ''}${panel ? ' with-panel' : ''}`}>
        {sidebarOpen && (
          <>
            <div className="scrim sidebar-scrim" onClick={() => setSidebarOpen(false)} />
            <Sidebar
              conversations={ws.conversations}
              currentId={ws.current?.id ?? null}
              statusOf={ws.statusOf}
              titleOf={ws.titleOf}
              onOpen={openConversation}
              onNew={() => {
                ws.newChat()
                setView('chat')
                if (narrow()) setSidebarOpen(false)
              }}
              onPerformance={() => {
                setView('performance')
                setPanel(null)
                if (narrow()) setSidebarOpen(false)
              }}
              performanceActive={view === 'performance'}
              onClose={() => setSidebarOpen(false)}
              llmReady={llmReady}
            />
          </>
        )}
        {view === 'performance' ? (
          <PerformanceView sidebarOpen={sidebarOpen} onOpenSidebar={() => setSidebarOpen(true)} />
        ) : (
          <Conversation ws={ws} sidebarOpen={sidebarOpen} onOpenSidebar={() => setSidebarOpen(true)} />
        )}
        {view === 'chat' && panel && caseId && (
          <SidePanel
            view={panel}
            caseId={caseId}
            state={ws.caseData?.state ?? null}
            events={ws.caseData?.events ?? []}
            reports={ws.caseData?.reports ?? {}}
            onNavigate={setPanel}
            onClose={() => setPanel(null)}
          />
        )}
      </div>
    </PanelContext.Provider>
  )
}
