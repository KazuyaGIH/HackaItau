import { useEffect, useState } from 'react'
import { api } from '../api'
import type { BenchmarkSummary } from '../types'

type Group = BenchmarkSummary['groups'][number]
type Entry = { label: string; model: string; tone: string; group: Group }
const decimal = (value: number) => value.toLocaleString('pt-BR', { maximumFractionDigits: 1 })
const usd = (value: number | null) => value === null ? 'Indisponível' : `US$ ${value.toLocaleString('pt-BR', { minimumFractionDigits: 4, maximumFractionDigits: 4 })}`
const cost = (group: Group) => group.usage_complete ? group.total_cost_usd : null
const rate = (group: Group) => group.runs > 0 ? 100 * group.automatic_passes / group.runs : 0

export function BenchmarkPanel({ refresh }: { refresh: number }) {
  const [data, setData] = useState<BenchmarkSummary | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let active = true
    api.benchmark().then(
      (result) => { if (active) { setData(result.benchmark); setError(false); setLoading(false) } },
      () => { if (active) { setError(true); setLoading(false) } },
    )
    return () => { active = false }
  }, [refresh])

  return (
    <section className="perf-section benchmark" aria-label="Comparativo executado">
      <h2>Squad comparada a um agente generalista</h2>
      {loading ? <p className="muted">Carregando comparativo…</p> : error ? (
        <p className="muted">Não foi possível carregar o comparativo. Tente atualizar novamente.</p>
      ) : !data ? (
        <p className="muted">Os resultados aparecerão aqui após a execução do benchmark.</p>
      ) : <Comparison data={data} />}
    </section>
  )
}

function Comparison({ data }: { data: BenchmarkSummary }) {
  const squad = data.groups.find((g) => g.architecture === 'squad' && /^gpt-4\.1-mini(?:-|$)/.test(g.model))
  const high = data.groups.find((g) => g.architecture === 'generalist' && /^gpt-5\.4(?:-|$)/.test(g.model) && g.reasoning_effort === 'high')
  const medium = data.groups.find((g) => g.architecture === 'generalist' && /^gpt-5\.2(?:-|$)/.test(g.model) && g.reasoning_effort === 'medium')
  const entries: Entry[] = []
  if (squad) entries.push({ label: 'Squad', model: 'GPT-4.1 mini', tone: 'squad', group: squad })
  if (high) entries.push({ label: 'Generalista 5.4', model: 'GPT-5.4 · raciocínio alto', tone: 'generalist', group: high })
  if (medium) entries.push({ label: 'Generalista 5.2', model: 'GPT-5.2 · raciocínio médio', tone: 'medium', group: medium })
  if (!entries.length) return <p className="muted">Este benchmark ainda não contém as configurações selecionadas.</p>

  const complete = data.status === 'complete'
  const matched = complete && squad && high && squad.runs > 0 && squad.runs === high.runs && squad.automatic_passes === high.automatic_passes
  const squadCost = squad ? cost(squad) : null
  const highCost = high ? cost(high) : null
  const savings = matched && squadCost !== null && highCost !== null && highCost > squadCost
    ? 100 * (1 - squadCost / highCost) : null
  const sameSample = entries.length === 3 && entries.every(({ group }) => group.runs === squad?.runs)
  const maxCost = Math.max(...entries.map(({ group }) => cost(group) ?? 0), 0.0001)

  return <>
    <p className="muted small">
      {data.published_snapshot ? 'Benchmark publicado' : 'Execuções reais'}
      {` · ${new Date(data.created_at).toLocaleDateString('pt-BR')}`}
      {sameSample ? ` · ${squad?.runs} casos sintéticos por configuração` : ' · amostras por configuração abaixo'}
      {complete ? '' : ' · resultado parcial'}.
    </p>
    {savings !== null && <div className="perf-hero benchmark-hero">
      <p className="hero-figure">{decimal(savings)}% menor custo</p>
      <p className="hero-caption">
        Squad com GPT-4.1 mini frente ao generalista com GPT-5.4 alto.
        Ambos passaram em {squad?.automatic_passes}/{squad?.runs} casos nas verificações automáticas.
      </p>
    </div>}
    <div className="benchmark-cards">
      {entries.map(({ label, model, tone, group }) => {
        const tied = matched && (group === squad || group === high)
        const worse = complete && group === medium && squad && high && group.runs === squad.runs && group.runs === high.runs
          && rate(group) < rate(squad) && rate(group) < rate(high)
        return <article className={`benchmark-card ${tone}`} key={tone}>
          <div>
            <h3>{label === 'Squad' ? 'Squad' : 'Generalista'}</h3>
            <p className="small muted">{model}</p>
          </div>
          <p className="benchmark-score">{group.automatic_passes}<span>/{group.runs} casos</span></p>
          <p className={`benchmark-verdict ${worse ? 'inferior' : ''}`}>
            {worse ? 'Resultado inferior neste teste' : tied ? 'Mesmo resultado automático' : 'Verificações automáticas'}
          </p>
          <dl className="benchmark-stats">
            <div><dt>Custo total</dt><dd>{usd(cost(group))}</dd></div>
            <div><dt>Tempo médio por caso</dt><dd>{decimal(group.mean_latency_seconds)} s</dd></div>
          </dl>
        </article>
      })}
    </div>
    <div className="compare">
      <figure className="bar-pair benchmark-chart">
        <figcaption>Custo total das execuções <span>Menor é melhor</span></figcaption>
        {entries.map((entry) => <ChartRow key={entry.tone} entry={entry}
          width={cost(entry.group) === null ? null : 100 * cost(entry.group)! / maxCost}
          value={usd(cost(entry.group))} />)}
        <p className="small muted">Entrada e saída, incluindo raciocínio, cache e novas tentativas.</p>
      </figure>
      <figure className="bar-pair benchmark-chart">
        <figcaption>Casos que passaram nas verificações <span>Maior é melhor</span></figcaption>
        {entries.map((entry) => <ChartRow key={entry.tone} entry={entry}
          width={entry.group.runs > 0 ? rate(entry.group) : null}
          value={entry.group.runs > 0 ? `${decimal(rate(entry.group))}%` : 'Sem execuções'} />)}
        <p className="small muted">Mesmos critérios de elegibilidade, risco e estruturação.</p>
      </figure>
    </div>
    <p className="small muted">
      Empate nas verificações automáticas; equivalência de qualidade ainda depende de revisão humana.
      Custos calculados com o consumo reportado e os preços configurados.
    </p>
  </>
}

function ChartRow({ entry, width, value }: { entry: Entry; width: number | null; value: string }) {
  return <div className="benchmark-bar-row">
    <span className="bar-label">{entry.label}</span>
    <span className="benchmark-bar-track" aria-hidden="true">
      {width !== null && <span className={`bar ${entry.tone}`} style={{ width: `${width}%` }} />}
    </span>
    <span className="bar-value">{value}</span>
  </div>
}
