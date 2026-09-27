import { Ban, CircleCheck, CornerUpLeft, PanelLeft, RefreshCw, ShieldCheck, TriangleAlert, Wrench } from 'lucide-react'
import { createElement, useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { DOMAIN_LABEL } from '../format'
import { agentIcon } from '../iconMap'
import { AGENT_META, toolLabel } from '../squad'
import type { AgentMetrics, Metrics } from '../types'
import { BenchmarkPanel } from './BenchmarkPanel'

const FORBIDDEN_LABEL: Record<string, string> = {
  approve_credit: 'aprovar crédito',
  reject_credit: 'rejeitar crédito',
  choose_numeric_assumptions: 'escolher premissas numéricas',
  define_stress_scenarios: 'definir cenários de estresse',
  define_thresholds: 'definir limites da política',
  estimate_repayment_capacity: 'estimar capacidade de pagamento',
  invent_evidence: 'inventar evidências',
  mark_preferred_alternative: 'marcar uma alternativa como preferida',
  propose_structure: 'propor estrutura',
  rank_alternatives: 'ranquear alternativas',
  read_client_financials: 'ler dados financeiros brutos',
  recompute_metrics: 'recalcular métricas',
  rewrite_outputs: 'reescrever resultados de outros agentes',
}

const n = (v: number) => v.toLocaleString('pt-BR')
// "1 acerto", "3 acertos"
const pl = (v: number, one: string, many: string) => `${n(v)} ${v === 1 ? one : many}`
const compact = (v: number) =>
  v >= 1e6
    ? `${(v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} mi`
    : v >= 1e4
      ? `${(v / 1e3).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} mil`
      : n(v)

interface Props {
  sidebarOpen: boolean
  onOpenSidebar: () => void
}

// Desempenho dos agentes desde que o servidor subiu. Tudo vem de /api/metrics (Event Log + resultados dos cases).
export function PerformanceView({ sidebarOpen, onOpenSidebar }: Props) {
  const [data, setData] = useState<Metrics | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [benchmarkRefresh, setBenchmarkRefresh] = useState(0)

  const fetchMetrics = useCallback(
    () =>
      api.metrics().then(
        (m) => {
          setData(m)
          setError(null)
          setLoading(false)
        },
        (e: Error) => {
          setError(e.message)
          setLoading(false)
        },
      ),
    [],
  )
  useEffect(() => {
    void fetchMetrics()
  }, [fetchMetrics])
  const reload = () => {
    setLoading(true)
    setBenchmarkRefresh((value) => value + 1)
    void fetchMetrics()
  }

  return (
    <main className="main">
      <header className="topbar">
        {!sidebarOpen && (
          <button type="button" className="icon-btn" onClick={onOpenSidebar} aria-label="Abrir barra lateral">
            <PanelLeft size={18} />
          </button>
        )}
        <p className="topbar-title">Desempenho dos agentes</p>
        <div className="topbar-actions">
          <button type="button" className="icon-btn with-label" onClick={reload} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spin' : undefined} />
            <span>Atualizar</span>
          </button>
        </div>
      </header>
      <div className="scroller">
        <div className="perf">
          <BenchmarkPanel refresh={benchmarkRefresh} />
          {error && (
            <div className="callout danger">
              <TriangleAlert size={16} />
              <p>Não consegui carregar as métricas: {error}</p>
            </div>
          )}
          {data && data.cases === 0 && (
            <div className="perf-empty">
              <h1>Ainda não há análises nas conversas</h1>
              <p className="muted">
                Rode uma análise numa conversa. As métricas contam desde que o servidor subiu, porque o estado fica em
                memória.
              </p>
            </div>
          )}
          {data && data.cases > 0 && (
            data.agents.every((a) => 'completion_pct' in a) ? <Dashboard m={data} /> : (
              <div className="callout warn">
                <TriangleAlert size={16} />
                <p>
                  O backend ainda está usando a definição anterior das métricas. Reinicie o servidor para carregar
                  a correção e depois atualize esta tela. Os casos atuais ficam em memória e serão perdidos ao reiniciar.
                </p>
              </div>
            )
          )}
        </div>
      </div>
    </main>
  )
}

function Dashboard({ m }: { m: Metrics }) {
  const ctx = m.context
  const calls = m.agents.reduce((s, a) => s + a.llm_calls, 0)
  return (
    <>
      <section className="perf-section">
        <h2>Uso nas conversas</h2>
        <p className="muted small">Atividade deste servidor desde a inicialização, separada do comparativo acima.</p>
      </section>

      <div className="kpis">
        <Kpi label="Cases registrados" value={n(m.cases)} note={`${n(m.reports)} com relatório`} />
        <Kpi label="Chamadas ao modelo" value={n(calls)} note={pl(m.human_decisions, 'decisão humana', 'decisões humanas')} />
        <Kpi
          label="Tokens reais (provedor)"
          value={compact(m.tokens.input + m.tokens.output)}
          note={`${compact(m.tokens.input)} de entrada, ${compact(m.tokens.output)} de saída`}
        />
        <Kpi
          label="Entrada média por chamada"
          value={`${compact(ctx.per_call_squad)} tokens estimados`}
          note="Estimativa pelo tamanho dos prompts dos especialistas"
        />
      </div>

      <section className="perf-section">
        <h2>Agentes</h2>
        <p className="muted small">
          Conclusão mede se a execução terminou, inclusive após correções; não mede se a análise está correta.
          Validação sem correções e devoluções da revisão são mostradas separadamente. Uma execução pode ter ambas as
          intervenções; elas não devem ser somadas como erros distintos. Contagem desde o início do servidor.
        </p>
        <div className="agent-cards">
          {m.agents.map((a) => (
            <AgentCard key={a.agent_id} a={a} />
          ))}
        </div>
      </section>
    </>
  )
}

function Kpi({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="kpi">
      <p className="kpi-label">{label}</p>
      <p className="kpi-value">{value}</p>
      <p className="kpi-note">{note}</p>
    </div>
  )
}

function AgentCard({ a }: { a: AgentMetrics }) {
  const pct = a.completion_pct
  const level = pct === null ? 'none' : pct >= 80 ? 'good' : pct >= 50 ? 'warn' : 'bad'
  const meta = AGENT_META[a.agent_id]
  return (
    <article className="agent-card">
      <header>
        <span className="node">{createElement(agentIcon(a.agent_id), { size: 16 })}</span>
        <div>
          <h3>{meta?.name ?? a.name}</h3>
          <p className="muted small">
            {a.name}, versão {a.version}
          </p>
        </div>
      </header>
      <p className="agent-desc">{a.description}</p>

      {a.reviewer ? (
        <div className="accuracy">
          <div className="accuracy-head">
            <span>Achados materiais ausentes na revisão seguinte</span>
            <strong>{a.reviewer.confirmation_pct === null ? 'sem dados' : `${Math.round(a.reviewer.confirmation_pct)}%`}</strong>
          </div>
          <Meter pct={a.reviewer.confirmation_pct} level="good" />
          <p className="small muted">
            {pl(a.reviewer.findings_raised, 'achado levantado', 'achados levantados')},{' '}
            {pl(a.reviewer.material_findings, 'material', 'materiais')},{' '}
            {pl(a.reviewer.reworks_triggered, 'retrabalho pedido', 'retrabalhos pedidos')},{' '}
            {pl(a.reviewer.confirmed_by_rework, 'ausente depois', 'ausentes depois')}.
          </p>
          <p className="small muted">O desaparecimento de um achado não comprova, por si só, que ele estava correto.</p>
        </div>
      ) : (
        <div className="accuracy">
          <div className="accuracy-head">
            <span>Conclusão das execuções encerradas</span>
            <strong>{pct === null ? 'sem execuções encerradas' : `${Math.round(pct)}%`}</strong>
          </div>
          <Meter pct={pct} level={level} />
          <ul className="outcomes">
            <li>
              <CircleCheck size={14} className="ok" />
              {pl(a.completed, 'concluída', 'concluídas')}
            </li>
            <li>
              <Wrench size={14} />
              {pl(a.validator_fixes, 'concluída com correções', 'concluídas com correções')}
            </li>
            <li>
              <CornerUpLeft size={14} className="warn" />
              {pl(a.reopened_by_review, 'devolvida pela revisão', 'devolvidas pela revisão')}
            </li>
            <li>
              <TriangleAlert size={14} className="bad" />
              {pl(a.failed, 'falha', 'falhas')}
            </li>
          </ul>
          <p className="small muted">
            Validação sem correções: {n(a.validation_clean)} de {n(a.completed)} concluídas
            {a.validation_first_pass_pct === null ? '.' : ` (${Math.round(a.validation_first_pass_pct)}%).`}
            {' '}Conclusão e validação não são medidas de acurácia factual.
          </p>
        </div>
      )}

      <dl className="agent-stats">
        <div>
          <dt>Tentativas iniciadas</dt>
          <dd className="num">{n(a.runs)}{a.in_progress > 0 ? ` (${n(a.in_progress)} em andamento)` : ''}</dd>
        </div>
        <div>
          <dt>Latência média</dt>
          <dd className="num">{a.avg_latency_ms === null ? '—' : `${(a.avg_latency_ms / 1000).toFixed(1).replace('.', ',')} s`}</dd>
        </div>
        <div>
          <dt>Contexto por chamada</dt>
          <dd className="num">{compact(a.avg_context_tokens)}</dd>
        </div>
        <div>
          <dt>Tokens reais</dt>
          <dd className="num">{compact(a.tokens_in + a.tokens_out)}</dd>
        </div>
        <div>
          <dt>Acessos a dados</dt>
          <dd className="num">{n(a.tool_calls)}</dd>
        </div>
        <div>
          <dt>Ajustes pedidos</dt>
          <dd className="num">{n(a.adjusted_by_human)}</dd>
        </div>
      </dl>

      <details className="can-do">
        <summary>O que pode e o que não pode fazer</summary>
        <p className="small">
          <strong>Ferramentas:</strong> {a.tools.map(toolLabel).join('; ')}.
        </p>
        <p className="small">
          <strong>Dados que pode ler:</strong> {a.data_domains.map((d) => DOMAIN_LABEL[d] ?? d).join(', ')}.
        </p>
        <p className="small forbidden">
          <Ban size={13} />
          <span>
            <strong>Não pode:</strong>{' '}
            {a.forbidden_actions.map((f) => FORBIDDEN_LABEL[f] ?? f.replace(/_/g, ' ')).join(', ')}.
          </span>
        </p>
        {a.denied_calls > 0 && (
          <p className="small">
            <ShieldCheck size={13} /> {n(a.denied_calls)} tentativa(s) de acesso negada(s) pelo backend.
          </p>
        )}
      </details>
    </article>
  )
}

function Meter({ pct, level }: { pct: number | null; level: string }) {
  return (
    <div
      className={`meter ${level}`}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct ?? 0}
      aria-label="Taxa"
    >
      <span style={{ width: `${pct ?? 0}%` }} />
    </div>
  )
}
