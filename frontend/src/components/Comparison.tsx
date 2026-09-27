// "Comparativo" da tela de entrada: squad × agente generalista, com todas as configurações executadas.
// Os números vêm do benchmark publicado ou local (GET /api/benchmarks/latest); nada é fixo no código.
// Sem benchmark (ou sem servidor) a seção não aparece.
import {
  archName,
  shortConfig,
  comparable,
  configName,
  cost,
  counterpart,
  decimal,
  headline,
  modelRank,
  useBenchmark,
  usd,
  type Group,
} from '../benchmark'
import type { BenchmarkSummary } from '../types'

export function Comparison() {
  const { data } = useBenchmark()
  if (!data || !data.groups.length) return null
  return <Body data={data} />
}

// uma linha por modelo (e esforço de raciocínio), com a squad e o generalista lado a lado
function rows(data: BenchmarkSummary) {
  const keyOf = (g: Group) => `${g.model}|${g.reasoning_effort ?? ''}`
  const map = new Map<string, { squad?: Group; generalist?: Group; rank: number }>()
  for (const g of data.groups) {
    const row = map.get(keyOf(g)) ?? { rank: modelRank(g) }
    row[g.architecture] = g
    map.set(keyOf(g), row)
  }
  return [...map.values()].sort((a, b) => a.rank - b.rank)
}

function Body({ data }: { data: BenchmarkSummary }) {
  const h = headline(data)
  const same = h ? counterpart(data, h.squad) : null
  const sameOk = h && same && comparable(data, h.squad, same) ? same : null
  const runs = data.groups[0].runs
  const byCost = data.groups.filter((g) => cost(g) !== null).sort((a, b) => cost(a)! - cost(b)!)
  const noCost = data.groups.filter((g) => cost(g) === null)
  const maxCost = Math.max(...byCost.map((g) => cost(g)!), 1e-9)
  const maxTime = Math.max(...byCost.map((g) => g.mean_latency_seconds), 1e-9)
  const cheaperSame = h && sameOk && cost(sameOk) !== null && cost(sameOk)! < cost(h.squad)! && sameOk.automatic_passes < sameOk.runs

  return (
    <section id="comparativo" className="cmp" aria-labelledby="cmp-title">
      <header className="cmp-intro">
        <p className="how-kicker mono">comparativo</p>
        <h2 id="cmp-title">
          {h ? `O mesmo ${runs}/${runs}, com um modelo menor.` : 'Squad e agente generalista, lado a lado.'}
        </h2>
        <p className="cmp-lede">
          Rodamos {runs} casos sintéticos de crédito agro de duas formas: com a squad de especialistas e com um único agente
          generalista que faz elegibilidade, risco e estruturação numa só resposta. Os dois recebem os mesmos dados, schemas,
          validadores, cálculos e revisão; muda só a arquitetura e o modelo.
        </p>
      </header>

      {h && (
        <div className="cmp-figures">
          {h.costRatio !== null && (
            <Figure
              big={`${decimal(h.costRatio)}×`}
              label={`menos custo para chegar a ${runs}/${runs}`}
              sub={`${usd(cost(h.squad))} na squad com ${configName(h.squad)}, contra ${usd(cost(h.generalist))} no generalista com ${configName(h.generalist)}, o mais barato a acertar todos.`}
            />
          )}
          <Figure
            big={`${decimal(h.timeRatio)}×`}
            label="mais rápido por caso"
            sub={`${decimal(h.squad.mean_latency_seconds, 0)} s em média na squad, contra ${decimal(h.generalist.mean_latency_seconds, 0)} s no generalista, nas mesmas configurações.`}
          />
          {sameOk && (
            <Figure
              big={`${h.squad.automatic_passes}/${h.squad.runs}`}
              bigSub={`× ${sameOk.automatic_passes}/${sameOk.runs}`}
              label={`squad × generalista, com o mesmo ${configName(h.squad)}`}
              sub="Mesmo modelo, mesmos dados e verificações dos dois lados: muda só a arquitetura."
            />
          )}
        </div>
      )}

      <div className="cmp-block">
        <h3>Casos aprovados, por modelo</h3>
        <p className="cmp-note">Cada quadrado é um caso; cheio quando passou em todas as verificações automáticas.</p>
        <div className="cmp-matrix" role="table" aria-label="Casos aprovados por modelo e arquitetura">
          <div className="cmp-mrow head" role="row">
            <span role="columnheader">Modelo</span>
            <span role="columnheader">Squad</span>
            <span role="columnheader">Generalista</span>
          </div>
          {rows(data).map((r) => {
            const any = (r.squad ?? r.generalist)!
            return (
              <div className="cmp-mrow" role="row" key={`${any.model}|${any.reasoning_effort ?? ''}`}>
                <span role="rowheader" className="cmp-model">
                  {configName(any)}
                </span>
                <Cell g={r.squad} />
                <Cell g={r.generalist} />
              </div>
            )
          })}
        </div>
      </div>

      <div className="cmp-block">
      <div className="cmp-charts">
        <Bars
          title={`Custo total dos ${runs} casos`}
          hint="menor é melhor"
          groups={byCost}
          width={(g) => (100 * cost(g)!) / maxCost}
          value={(g) => usd(cost(g))}
        />
        <Bars
          title="Tempo médio por caso"
          hint="menor é melhor"
          groups={byCost}
          width={(g) => (100 * g.mean_latency_seconds) / maxTime}
          value={(g) => `${decimal(g.mean_latency_seconds, 0)} s`}
        />
      </div>
      <p className="cmp-legend mono" aria-hidden="true">
        <span>
          <i className="is-squad" /> squad
        </span>
        <span>
          <i className="is-generalist" /> generalista
        </span>
        <span>· ordem pelo custo · ✓ acertou todos os casos</span>
      </p>
      {noCost.length > 0 && (
        <p className="cmp-note">
          Sem custo total: {noCost.map((g) => `${archName(g).toLowerCase()} com ${configName(g)}`).join(', ')} (o provedor não
          informou o consumo de todas as chamadas; o custo fica indisponível, não zero).
        </p>
      )}
      </div>

      <div className="cmp-block">
        <h3>Como ler</h3>
        <ul className="cmp-caveats">
          {cheaperSame && h && sameOk && (
            <li>
              Com o mesmo {configName(h.squad)}, o generalista custou menos ({usd(cost(sameOk))} contra {usd(cost(h.squad))}),
              mas passou em {sameOk.automatic_passes} de {sameOk.runs}. A squad faz mais chamadas, cada uma com contexto menor.
            </li>
          )}
          <li>
            As verificações automáticas medem restrições: bloqueio esperado, premissas numéricas, limites de produtos,
            referências e códigos de risco. Não medem acurácia factual; a revisão humana às cegas
            {data.quality_status === 'reviewed' ? ' já foi feita.' : ' ainda está pendente.'}
          </li>
          <li>
            São {runs} casos conhecidos, uma execução por configuração: um resultado exploratório, não prova de
            superioridade.
          </li>
          <li>
            O custo soma todas as chamadas, inclusive correções e retrabalho, com preços de API de referência. Não é fatura
            e não inclui infraestrutura.
          </li>
        </ul>
        <p className="cmp-meta mono">
          {data.published_snapshot ? 'benchmark publicado' : 'execução local'} · {new Date(data.created_at).toLocaleDateString('pt-BR')}
          {data.status === 'complete' ? '' : ' · parcial'} · {data.run_id}
        </p>
      </div>
    </section>
  )
}

function Figure({ big, bigSub, label, sub }: { big: string; bigSub?: string; label: string; sub: string }) {
  return (
    <div className="cmp-figure">
      <p className="cmp-big">
        {big}
        {bigSub && <span>{bigSub}</span>}
      </p>
      <p className="cmp-label">{label}</p>
      <p className="cmp-sub">{sub}</p>
    </div>
  )
}

function Cell({ g }: { g?: Group }) {
  if (!g) {
    return (
      <span role="cell" className="cmp-cell is-none mono">
        não testado
      </span>
    )
  }
  const c = cost(g)
  return (
    <span role="cell" className={`cmp-cell is-${g.architecture}`}>
      <span className="cmp-pips" aria-hidden="true">
        {Array.from({ length: g.runs }, (_, i) => (
          <i key={i} className={i < g.automatic_passes ? 'on' : ''} />
        ))}
      </span>
      <span className="cmp-score">
        {g.automatic_passes}/{g.runs}
      </span>
      <span className="cmp-cell-sub mono">
        {c === null ? 'custo indisponível' : usd(c)} · {decimal(g.mean_latency_seconds, 0)} s
        {g.errors > 0 && ` · ${g.errors} ${g.errors === 1 ? 'falha operacional' : 'falhas operacionais'}`}
      </span>
    </span>
  )
}

function Bars({
  title,
  hint,
  groups,
  width,
  value,
}: {
  title: string
  hint: string
  groups: Group[]
  width: (g: Group) => number
  value: (g: Group) => string
}) {
  return (
    <figure className="cmp-chart">
      <figcaption>
        {title} <span className="mono">{hint}</span>
      </figcaption>
      {groups.map((g) => {
        const name = `${archName(g)} · ${shortConfig(g)}`
        return (
          <div className="cmp-bar-row" key={`${g.architecture}|${g.model}|${g.reasoning_effort ?? ''}`} title={`${name}: ${value(g)} · ${g.automatic_passes}/${g.runs} casos`}>
            <span className="cmp-bar-label">
              {name}
              {g.automatic_passes === g.runs && <b aria-label="acertou todos os casos"> ✓</b>}
            </span>
            <span className="cmp-bar-track">
              <span className={`cmp-bar is-${g.architecture}`} style={{ width: `${Math.max(width(g), 0.6)}%` }} />
            </span>
            <span className="cmp-bar-value mono">{value(g)}</span>
          </div>
        )
      })}
    </figure>
  )
}
