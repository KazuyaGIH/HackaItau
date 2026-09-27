// Resumo do comparativo em Desempenho dos agentes: só as comparações diretas.
// O comparativo completo (todas as configurações, custos e ressalvas) fica na tela de entrada.
import { comparable, configName, counterpart, decimal, headline, useBenchmark, usd } from '../benchmark'
import type { BenchmarkSummary } from '../types'

export function BenchmarkPanel({ refresh }: { refresh: number }) {
  const { data, error, loading } = useBenchmark(refresh)
  return (
    <section className="perf-section bench-mini" aria-label="Comparativo com agente generalista">
      <h2>Comparativo com agente generalista</h2>
      {loading ? (
        <p className="muted small">Carregando comparativo…</p>
      ) : error ? (
        <p className="muted small">Não foi possível carregar o comparativo.</p>
      ) : !data ? (
        <p className="muted small">Os resultados aparecerão aqui após a execução do benchmark.</p>
      ) : (
        <Summary data={data} />
      )}
    </section>
  )
}

function Summary({ data }: { data: BenchmarkSummary }) {
  const h = headline(data)
  const same = h && counterpart(data, h.squad)
  const runs = h?.squad.runs
  return (
    <>
      <p className="muted small">
        {data.published_snapshot ? 'Benchmark publicado' : 'Execuções reais'} · {new Date(data.created_at).toLocaleDateString('pt-BR')}
        {runs ? ` · ${runs} casos sintéticos por configuração` : ''}
        {data.status === 'complete' ? '' : ' · resultado parcial'} · verificações automáticas, revisão humana pendente.
      </p>
      {!h ? (
        <p className="muted small">Ainda não há uma configuração de cada lado que tenha passado em todos os casos.</p>
      ) : (
        <div className="bench-mini-row">
          <Stat
            label={`Custo para chegar a ${runs}/${runs}`}
            squad={usd(h.squad.total_cost_usd)}
            generalist={usd(h.generalist.total_cost_usd)}
            note={`${configName(h.squad)} × ${configName(h.generalist)}${h.costRatio ? ` · ${decimal(h.costRatio)}× menor` : ''}`}
          />
          <Stat
            label="Tempo médio por caso"
            squad={`${decimal(h.squad.mean_latency_seconds, 0)} s`}
            generalist={`${decimal(h.generalist.mean_latency_seconds, 0)} s`}
            note={`mesmas configurações · ${decimal(h.timeRatio)}× mais rápido`}
          />
          {same && comparable(data, h.squad, same) && (
            <Stat
              label={`Mesmo modelo (${configName(h.squad)})`}
              squad={`${h.squad.automatic_passes}/${h.squad.runs}`}
              generalist={`${same.automatic_passes}/${same.runs}`}
              note="casos aprovados nas verificações automáticas"
            />
          )}
        </div>
      )}
      <p className="muted small">Todas as configurações e ressalvas estão na tela de entrada, na seção Comparativo.</p>
    </>
  )
}

function Stat({ label, squad, generalist, note }: { label: string; squad: string; generalist: string; note: string }) {
  return (
    <div className="bench-mini-stat">
      <p className="bench-mini-label">{label}</p>
      <dl>
        <div>
          <dt>Squad</dt>
          <dd>{squad}</dd>
        </div>
        <div>
          <dt>Generalista</dt>
          <dd>{generalist}</dd>
        </div>
      </dl>
      <p className="bench-mini-note">{note}</p>
    </div>
  )
}
