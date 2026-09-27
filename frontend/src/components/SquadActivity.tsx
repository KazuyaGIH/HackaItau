import { ChevronDown, CornerUpLeft, Users } from 'lucide-react'
import { createElement, useState } from 'react'
import { ELIGIBILITY_LABEL } from '../format'
import { formatElapsed, useNow } from '../hooks'
import { STEP_ICON, agentIcon } from '../iconMap'
import { AGENT_META, REVIEW, agentName, currentActivity, teamsFor, type Step } from '../squad'
import type { ActivityBlock, AgentRun } from '../transcript'
import type { CaseState, Finding } from '../types'
import { SourceChip } from './SourceChip'
import { OrchestratorMark } from './ui'

const STATUS_TEXT: Record<AgentRun['status'], string> = {
  queued: 'na fila',
  running: 'trabalhando',
  done: 'concluído',
  reopened: 'reaberto',
  failed: 'falhou',
  blocked: 'bloqueado',
}

const PHASE_TITLE: Record<ActivityBlock['phase'], [string, string]> = {
  execution: ['A squad está analisando a demanda', 'A squad concluiu a análise'],
  human_adjustment: ['A squad está aplicando o seu ajuste', 'A squad aplicou o seu ajuste'],
  retry: ['A squad está retomando o trabalho', 'A squad retomou e concluiu o trabalho'],
}

interface Props {
  block: ActivityBlock
  state: CaseState | null
}

export function SquadActivity({ block, state }: Props) {
  const running = block.status === 'running'
  const [open, setOpen] = useState<boolean | null>(null)
  const expanded = open ?? running
  const now = useNow(running)
  const elapsed = formatElapsed((block.endTs ? Date.parse(block.endTs) : now) - Date.parse(block.startTs))
  const teams = teamsFor(block.order)
  const active = block.order.map((id) => block.agents[id]).find((a) => a.status === 'running')
  const reworks = block.reviews.filter((r) => r.reopen).length

  const title =
    block.status === 'failed'
      ? `A squad parou em ${agentName(block.failedAgent)}`
      : block.status === 'blocked'
        ? 'A squad precisa de uma informação para continuar'
        : PHASE_TITLE[block.phase][running ? 0 : 1]

  const meta = [
    `${block.order.length} agentes em ${teams.length} ${teams.length === 1 ? 'time' : 'times'}`,
    `${block.toolCalls} acessos autorizados`,
    reworks ? `${reworks} retrabalho${reworks > 1 ? 's' : ''}` : null,
    elapsed,
  ].filter(Boolean)

  return (
    <section className={`squad ${block.status}`} aria-label="Trabalho da squad">
      <button type="button" className="squad-head" onClick={() => setOpen(!expanded)} aria-expanded={expanded}>
        <OrchestratorMark live={running} size={24} />
        <span className="squad-title">
          <span className={running ? 'shimmer' : ''}>{title}</span>
          {running && active ? (
            <span className="squad-now">
              {agentName(active.agentId)}: {activityText(active, now)}
            </span>
          ) : (
            <span className="squad-meta">{meta.join(', ')}</span>
          )}
        </span>
        {(block.denied > 0 || block.security > 0) && (
          <span className="squad-flag">
            {block.denied + block.security} alerta{block.denied + block.security > 1 ? 's' : ''} de segurança
          </span>
        )}
        <ChevronDown className="chev" size={18} />
      </button>

      <div className={`collapsible${expanded ? ' open' : ''}`}>
        <div>
          <div className="squad-body">
            {teams.map((team) => {
              const done = team.agents.filter((id) => block.agents[id]?.status === 'done').length
              return (
                <div className="team" key={team.id}>
                  <div className="team-head">
                    <Users size={15} />
                    <span>{team.name}</span>
                    <span className="team-progress">
                      {done} de {team.agents.length}
                    </span>
                  </div>
                  <ol className="relay">
                    {team.agents.map((id, i) => (
                      <AgentRow
                        key={id}
                        run={block.agents[id]}
                        state={state}
                        now={now}
                        blockStatus={block.status}
                        index={i}
                      />
                    ))}
                  </ol>
                </div>
              )
            })}
            {block.reviews
              .filter((r) => r.reopen)
              .map((r) => (
                <ReworkLine key={r.round} reopen={r.reopen!} findingIds={r.findingIds} state={state} round={r.round} />
              ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function activityText(run: AgentRun, now: number): string {
  const last = run.lastEvent
  // tool calls são instantâneas: se a última foi há um tempo, o agente está esperando o modelo
  if (last?.type === 'TOOL_CALLED' && now - Date.parse(last.ts) > 900) return 'Analisando as evidências com o modelo'
  return currentActivity(last ?? undefined)
}

interface RowProps {
  run: AgentRun
  state: CaseState | null
  now: number
  blockStatus: ActivityBlock['status']
  index: number
}

function AgentRow({ run, state, now, blockStatus, index }: RowProps) {
  const [showSteps, setShowSteps] = useState(false)
  // o case falhou com o agente no meio do trabalho: ele não está mais trabalhando
  const status = blockStatus === 'failed' && (run.status === 'running' || run.status === 'reopened') ? 'failed' : run.status
  const card = state?.agents.find((a) => a.agent_id === run.agentId)
  const isLatest = card?.round === run.round
  const headline = status === 'done' && isLatest ? agentHeadline(run.agentId, card?.output ?? null) : null
  // ao vivo: os últimos passos, sem repetir a reabertura que já aparece na nota acima
  const steps = status === 'running' ? run.steps.filter((s) => s.kind !== 'reopen').slice(-4) : run.steps

  return (
    <li className={`agent-row ${status}`} style={{ ['--i' as string]: index }}>
      <span className="node" aria-hidden="true">
        {createElement(agentIcon(run.agentId), { size: 15 })}
      </span>
      <div className="agent-body">
        <div className="agent-line">
          <span className="agent-name">{AGENT_META[run.agentId]?.name ?? run.agentId}</span>
          <span className="agent-role">{AGENT_META[run.agentId]?.role}</span>
          <span className="agent-status">
            {run.round > 1 && <span className="round">rodada {run.round}</span>}
            {STATUS_TEXT[status]}
          </span>
        </div>
        {run.reopenedBy && status !== 'done' && (
          <div className="agent-note">
            <CornerUpLeft size={13} />
            {run.reopenedBy === 'human' ? 'Reaberto pelo seu ajuste' : 'Reaberto pelo Revisor'}
          </div>
        )}
        {status === 'running' && <div className="agent-now shimmer">{activityText(run, now)}</div>}
        {headline && <div className="agent-result">{headline}</div>}
        {(status === 'running' || showSteps) && steps.length > 0 && <StepList steps={steps} />}
        {status !== 'running' && run.steps.length > 0 && (
          <div className="agent-links">
            <button type="button" className="link" onClick={() => setShowSteps(!showSteps)}>
              {showSteps ? 'Ocultar passos' : `Ver ${run.steps.length} passos`}
            </button>
            {run.outputIds.length > 0 && <SourceChip id={run.outputIds[run.outputIds.length - 1]} label="resultado" />}
          </div>
        )}
      </div>
    </li>
  )
}

function StepList({ steps }: { steps: Step[] }) {
  return (
    <ul className="steps">
      {steps.map((s) => (
        <li key={s.seq} className={s.tone}>
          {createElement(STEP_ICON[s.kind], { size: 13 })}
          <span>{s.text}</span>
        </li>
      ))}
    </ul>
  )
}

function ReworkLine({
  reopen,
  findingIds,
  state,
  round,
}: {
  reopen: string
  findingIds: string[]
  state: CaseState | null
  round: number
}) {
  const findings = new Map<string, Finding>((state?.review?.findings ?? []).map((f) => [f.id, f]))
  const main = findingIds.map((id) => findings.get(id)).find((f) => f && f.owner_agent === reopen && f.severity === 'high')
  return (
    <div className="rework-line">
      <CornerUpLeft size={15} />
      <p>
        Na revisão da rodada {round}, o {agentName(REVIEW)} encontrou um problema material e devolveu a tarefa para{' '}
        {agentName(reopen)}.{main ? ` ${main.message.replace(/`/g, '')}` : ''}
      </p>
    </div>
  )
}

function agentHeadline(agentId: string, output: Record<string, unknown> | null): string | null {
  if (!output) return null
  if (agentId === 'agro_eligibility' && output.status) {
    return `Status: ${ELIGIBILITY_LABEL[String(output.status)] ?? String(output.status)}`
  }
  if (agentId === 'agro_credit_risk' && Array.isArray(output.main_risks)) {
    return `${output.main_risks.length} riscos principais, sobre métricas calculadas por código`
  }
  if (agentId === 'agro_structuring' && Array.isArray(output.alternatives)) {
    return `${output.alternatives.length} estruturas comparáveis, sem preferência do sistema`
  }
  if (agentId === REVIEW && typeof output.overall_assessment === 'string') return output.overall_assessment
  return null
}

