import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { Conversation } from './components/Conversation'
import { Landing, type SignIn } from './components/Landing'
import { PerformanceView } from './components/PerformanceView'
import { SidePanel } from './components/SidePanel'
import { Sidebar } from './components/Sidebar'
import { PanelContext, type PanelApi, type PanelView } from './panel'
import { useSession } from './session'
import { withTransition } from './transition'
import type { Identity } from './types'
import { useWorkspace } from './workspace'

const narrow = () => typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches

export default function App() {
  const { user, signIn, signOut } = useSession()
  const [entering, setEntering] = useState(false)

  const enter: SignIn = (u, from) =>
    withTransition(
      'enter',
      () => {
        signIn(u)
        setEntering(true)
      },
      from,
    )
  const leave = () => withTransition('leave', signOut)
  const entered = useCallback(() => setEntering(false), [])

  if (!user) return <Landing onSignIn={enter} />
  // key: trocar de usuário recria o workspace (conversas e cases são de cada um)
  return (
    <>
      {/* anel de luz na borda da abertura; só existe durante a entrada (ver .vt-glow em index.css) */}
      {entering && <div className="vt-glow" aria-hidden="true" />}
      <Workspace key={user.user_id} user={user} onSignOut={leave} entering={entering} onEntered={entered} />
    </>
  )
}

interface WorkspaceProps {
  user: Identity
  onSignOut: () => void
  entering: boolean // acabou de entrar: os elementos sobem em cascata
  onEntered: () => void
}

function Workspace({ user, onSignOut, entering, onEntered }: WorkspaceProps) {
  const ws = useWorkspace(user.user_id)
  const [llmReady, setLlmReady] = useState<boolean | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(() => !narrow())
  const [panel, setPanel] = useState<PanelView | null>(null)
  const [reportFullscreen, setReportFullscreen] = useState(false)
  const [view, setView] = useState<'chat' | 'performance'>('chat')

  const closePanel = () => {
    setPanel(null)
    setReportFullscreen(false)
  }

  useEffect(() => {
    if (!reportFullscreen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setReportFullscreen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [reportFullscreen])

  useEffect(() => {
    if (!entering) return
    const t = window.setTimeout(onEntered, 1500)
    return () => window.clearTimeout(t)
  }, [entering, onEntered])

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
    setReportFullscreen(false)
  }

  const panelApi = useMemo<PanelApi>(
    () => ({
      caseId,
      view: panel,
      open: setPanel,
      openEvidence: (id) => setPanel((v) => ({ kind: 'evidence', id, back: v?.kind === 'evidence' ? v.back : v })),
      close: closePanel,
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
      <div
        className={`app${entering ? ' entering' : ''}${sidebarOpen ? ' with-sidebar' : ''}${panel ? ' with-panel' : ''}${
          panel && reportFullscreen && view === 'chat' ? ' report-fullscreen' : ''
        }`}
      >
        {sidebarOpen && (
          <>
            <div className="scrim sidebar-scrim" onClick={() => setSidebarOpen(false)} />
            <Sidebar
              conversations={ws.conversations}
              currentId={ws.current?.id ?? null}
              statusOf={ws.statusOf}
              titleOf={ws.titleOf}
              onOpen={openConversation}
              onDelete={ws.deleteConversation}
              onNew={() => {
                ws.newChat()
                setView('chat')
                if (narrow()) setSidebarOpen(false)
              }}
              onPerformance={() => {
                setView('performance')
                closePanel()
                if (narrow()) setSidebarOpen(false)
              }}
              performanceActive={view === 'performance'}
              onClose={() => setSidebarOpen(false)}
              llmReady={llmReady}
              user={user}
              onSignOut={onSignOut}
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
            fullscreen={reportFullscreen}
            onToggleFullscreen={() => setReportFullscreen((f) => !f)}
            onNavigate={setPanel}
            onClose={closePanel}
          />
        )}
      </div>
    </PanelContext.Provider>
  )
}
