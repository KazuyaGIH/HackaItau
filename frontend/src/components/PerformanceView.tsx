import { Ban, CircleCheck, CornerUpLeft, PanelLeft, RefreshCw, ShieldCheck, TriangleAlert, Wrench } from 'lucide-react'
import { createElement, useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { DOMAIN_LABEL } from '../format'
import { agentIcon } from '../iconMap'
import { AGENT_META, toolLabel } from '../squad'
import type { AgentMetrics, Metrics } from '../types'
import { AsciiField } from './AsciiField'

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
      <AsciiField className="empty-field" />
      <div className="scroller">
        <div className="perf">
          {error && (
            <div className="callout danger">
              <TriangleAlert size={16} />
              <p>Não consegui carregar as métricas: {error}</p>
            </div>
          )}
          {data && data.cases === 0 && (
            <div className="perf-empty">
              <h1>Ainda não há execuções para medir</h1>
              <p className="muted">
                Rode uma análise numa conversa. As métricas contam desde que o servidor subiu, porque o estado fica em
                memória.
              </p>
            </div>
          )}
          {data && data.cases > 0 && <Dashboard m={data} />}
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
      <section className="perf-hero" aria-label="Contexto por chamada">
        {ctx.per_call_saved_pct !== null ? (
          <>
            <p className="hero-figure">{Math.round(ctx.per_call_saved_pct)}% menos contexto</p>
            <p className="hero-caption">
              por chamada ao modelo, comparado a um agente generalista que recebesse todas as evidências do case e os
              playbooks de todos os especialistas.
            </p>
          </>
        ) : (
          <p className="hero-caption">Sem chamadas ao modelo medidas ainda.</p>
        )}
      </section>

      <div className="kpis">
        <Kpi label="Cases analisados" value={n(m.cases)} note={`${n(m.reports)} com relatório`} />
        <Kpi label="Chamadas ao modelo" value={n(calls)} note={pl(m.human_decisions, 'decisão humana', 'decisões humanas')} />
        <Kpi
          label="Tokens reais (provedor)"
          value={compact(m.tokens.input + m.tokens.output)}
          note={`${compact(m.tokens.input)} de entrada, ${compact(m.tokens.output)} de saída`}
        />
        <Kpi
          label="Contexto evitado por chamada"
          value={`${compact(Math.max(0, ctx.per_call_generalist - ctx.per_call_squad))} tokens`}
          note={`${compact(ctx.per_call_squad)} na squad contra ${compact(ctx.per_call_generalist)} no generalista`}
        />
      </div>

      <section className="perf-section">
        <h2>Squad comparada a um agente generalista</h2>
        <p className="muted small">
          Tokens estimados pelo tamanho real dos prompts (cerca de 4 caracteres por token). O generalista faria uma chamada
          por rodada de análise, sempre com todo o contexto.
        </p>
        <div className="legend" aria-hidden="true">
          <span>
            <i className="key squad" />
            Squad
          </span>
          <span>
            <i className="key generalist" />
            Agente generalista (estimado)
          </span>
        </div>
        <div className="compare">
          <BarPair
            title="Contexto médio por chamada"
            squad={ctx.per_call_squad}
            generalist={ctx.per_call_generalist}
            note={`${n(ctx.squad_calls)} chamadas da squad, ${n(ctx.generalist_calls)} do generalista`}
          />
          <BarPair
            title="Contexto total enviado"
            squad={ctx.squad_tokens}
            generalist={ctx.generalist_tokens}
            note={
              ctx.saved_tokens >= 0
                ? `A squad enviou ${compact(ctx.saved_tokens)} tokens a menos no total.`
                : `No total a squad enviou ${compact(-ctx.saved_tokens)} tokens a mais: faz mais chamadas, incluindo a revisão e o retrabalho.`
            }
          />
        </div>
        <details className="numbers">
          <summary>Ver os números em tabela</summary>
          <table className="table">
            <thead>
              <tr>
                <th>Medida</th>
                <th>Squad</th>
                <th>Generalista (estimado)</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Contexto por chamada (tokens)</td>
                <td className="num">{n(ctx.per_call_squad)}</td>
                <td className="num">{n(ctx.per_call_generalist)}</td>
              </tr>
              <tr>
                <td>Contexto total (tokens)</td>
                <td className="num">{n(ctx.squad_tokens)}</td>
                <td className="num">{n(ctx.generalist_tokens)}</td>
              </tr>
              <tr>
                <td>Chamadas ao modelo</td>
                <td className="num">{n(ctx.squad_calls)}</td>
                <td className="num">{n(ctx.generalist_calls)}</td>
              </tr>
            </tbody>
          </table>
        </details>
      </section>

      <section className="perf-section">
        <h2>Agentes</h2>
        <p className="muted small">
          Acerto: execução concluída que passou pelo validador de primeira e não foi devolvida pela revisão. Erro: a revisão
          devolveu a tarefa ou a execução falhou.
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

function BarPair({ title, squad, generalist, note }: { title: string; squad: number; generalist: number; note: string }) {
  const max = Math.max(squad, generalist, 1)
  const row = (label: string, value: number, cls: string) => (
    <div className="bar-row" title={`${label}: ${n(value)} tokens`}>
      <span className="bar-label">{label}</span>
      <span className="bar-track">
        <span className={`bar ${cls}`} style={{ width: `${Math.max(2, (100 * value) / max)}%` }} />
        <span className="bar-value">{compact(value)}</span>
      </span>
    </div>
  )
  return (
    <figure className="bar-pair">
      <figcaption>{title}</figcaption>
      {row('Squad', squad, 'squad')}
      {row('Generalista', generalist, 'generalist')}
      <p className="small muted">{note}</p>
    </figure>
  )
}

function AgentCard({ a }: { a: AgentMetrics }) {
  const pct = a.accuracy_pct
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
            <span>Problemas materiais confirmados pelo retrabalho</span>
            <strong>{a.reviewer.confirmation_pct === null ? 'sem dados' : `${Math.round(a.reviewer.confirmation_pct)}%`}</strong>
          </div>
          <Meter pct={a.reviewer.confirmation_pct} level="good" />
          <p className="small muted">
            {pl(a.reviewer.findings_raised, 'achado levantado', 'achados levantados')},{' '}
            {pl(a.reviewer.material_findings, 'material', 'materiais')},{' '}
            {pl(a.reviewer.reworks_triggered, 'retrabalho pedido', 'retrabalhos pedidos')},{' '}
            {pl(a.reviewer.confirmed_by_rework, 'corrigido depois', 'corrigidos depois')}.
          </p>
        </div>
      ) : (
        <div className="accuracy">
          <div className="accuracy-head">
            <span>Taxa de acerto</span>
            <strong>{pct === null ? 'sem execuções' : `${Math.round(pct)}%`}</strong>
          </div>
          <Meter pct={pct} level={level} />
          <ul className="outcomes">
            <li>
              <CircleCheck size={14} className="ok" />
              {pl(a.hits, 'acerto', 'acertos')}
            </li>
            <li>
              <Wrench size={14} />
              {pl(a.validator_fixes, 'corrigida pelo validador', 'corrigidas pelo validador')}
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
        </div>
      )}

      <dl className="agent-stats">
        <div>
          <dt>Execuções</dt>
          <dd className="num">{n(a.completed)}</dd>
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
