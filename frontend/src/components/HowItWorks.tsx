// "Como funciona": um diagrama fixo que se monta conforme as legendas passam, com a trilha de auditoria embaixo.
// A seção não tem fundo próprio: rola sobre o mesmo campo ASCII da primeira tela.
// Duas versões do mesmo desenho (horizontal e vertical); o CSS mostra uma conforme a largura da tela.
// Com prefers-reduced-motion o diagrama já aparece completo e sem animação.
import { useEffect, useRef, useState, type ReactNode } from 'react'

type Pt = [number, number]

const CAPTIONS = [
  'A demanda entra: R$ 50 mi para custeio de soja.',
  'O orquestrador monta a squad certa para ela.',
  'Cada agente recebe só os dados de que precisa.',
  'O Revisor acha um problema e devolve ao Risco.',
  'Quem decide é uma pessoa, não a IA.',
]

// ids e eventos reais do backend (agent cards, resource_policies.json, EventType)
const AGENTS: Array<{ id: string; name: string; pills: Array<[string, boolean]> }> = [
  { id: 'agro_eligibility', name: 'Elegibilidade', pills: [['cadastro', true], ['perfil agro', true], ['documentos', true]] },
  { id: 'agro_credit_risk', name: 'Risco', pills: [['financials', true], ['mercado', true], ['cálculos', true]] },
  { id: 'agro_structuring', name: 'Estruturação', pills: [['catálogo', true], ['financials', false]] },
]

type Tone = 'ok' | 'deny' | 'accent'
const AUDIT: Array<{ at: number; who: string; what: string; note?: string; tone?: Tone }> = [
  { at: 1, who: 'orchestrator', what: 'CASE_CREATED', note: 'custeio soja · R$ 50 mi' },
  { at: 2, who: 'orchestrator', what: 'AGENT_SELECTED', note: '4 agentes' },
  { at: 3, who: 'agro_eligibility', what: 'PERMISSION_CHECKED', note: 'agro_profile · ok', tone: 'ok' },
  { at: 3, who: 'agro_credit_risk', what: 'PERMISSION_CHECKED', note: 'client_financials · ok', tone: 'ok' },
  { at: 3, who: 'agro_structuring', what: 'PERMISSION_DENIED', note: 'client_financials', tone: 'deny' },
  { at: 4, who: 'credit_review', what: 'REVIEW_ISSUE_FOUND', note: 'estresse de preço', tone: 'accent' },
  { at: 4, who: 'agro_credit_risk', what: 'TASK_REOPENED' },
  { at: 4, who: 'agro_credit_risk', what: 'CALC-STRESS-R2', note: 'ok', tone: 'ok' },
  { at: 5, who: 'orchestrator', what: 'HUMAN_REVIEW_REQUIRED', note: 'aguardando analista' },
]

const pad = (n: number) => String(n).padStart(3, '0')

// ponta de seta em `tip`, apontando na direção from → tip
function head(tip: Pt, from: Pt, size = 7): string {
  const [x, y] = tip
  const a = Math.atan2(y - from[1], x - from[0])
  const p = (da: number): Pt => [x - size * Math.cos(a + da), y - size * Math.sin(a + da)]
  const [l, r] = [p(0.45), p(-0.45)]
  return `M${l[0]} ${l[1]} L${x} ${y} L${r[0]} ${r[1]}`
}

interface Ctx {
  shown: number
  active: number
}

const cls = (c: Ctx, at: number, activeAt: number | number[] = at, extra = '') => {
  const act = Array.isArray(activeAt) ? activeAt.includes(c.active) : c.active === activeAt
  return `d-el${c.shown >= at ? ' on' : ''}${act && c.shown >= at ? ' act' : ''}${extra ? ` ${extra}` : ''}`
}

function Edge({ c, at, activeAt, d, tip, from, extra }: { c: Ctx; at: number; activeAt?: number; d: string; tip: Pt; from: Pt; extra?: string }) {
  return (
    <g className={cls(c, at, activeAt ?? at, `edge${extra ? ` ${extra}` : ''}`)}>
      <path d={d} pathLength={1} />
      <path className="head" d={head(tip, from)} />
    </g>
  )
}

const PILL_H = 18
const pillW = (label: string, denied: boolean) => label.length * 6 + 14 + (denied ? 11 : 0)

function Pills({ c, x, y, pills }: { c: Ctx; x: number; y: number; pills: Array<[string, boolean]> }) {
  let cx = x
  const out: ReactNode[] = []
  for (const [label, ok] of pills) {
    const w = pillW(label, !ok)
    const x0 = cx
    out.push(
      <g key={label + ok} className={`pill ${ok ? 'ok' : 'deny'}`}>
        <rect x={x0} y={y} width={w} height={PILL_H} rx={PILL_H / 2} />
        {!ok && <path className="x" d={`M${x0 + 8} ${y + 6} l6 6 M${x0 + 14} ${y + 6} l-6 6`} />}
        <text x={x0 + 7 + (ok ? 0 : 11)} y={y + 12.5}>
          {label}
        </text>
        {!ok && <line x1={x0 + 18} x2={x0 + w - 6} y1={y + 9} y2={y + 9} />}
      </g>,
    )
    cx += w + 5
    if (!ok) {
      out.push(
        <text key="negado" className="deny-label" x={cx + 1} y={y + 12.5}>
          negado
        </text>,
      )
    }
  }
  return <g className={cls(c, 3, 3, 'pills')}>{out}</g>
}

function Agent({ c, a, x, y, w, h, compact }: { c: Ctx; a: (typeof AGENTS)[number]; x: number; y: number; w: number; h: number; compact?: boolean }) {
  const risk = a.id === 'agro_credit_risk'
  return (
    <g>
      <g className={cls(c, 2, risk ? [3, 4] : 3, 'node')}>
        <rect x={x} y={y} width={w} height={h} rx={12} />
        <text className="n-name" x={x + (compact ? 12 : 14)} y={y + (compact ? 22 : 28)}>
          {a.name}
        </text>
        <text
          className="n-id"
          x={compact ? x + w - 12 : x + 14}
          y={y + (compact ? 22 : 46)}
          textAnchor={compact ? 'end' : 'start'}
        >
          {a.id}
        </text>
      </g>
      <Pills c={c} x={x + (compact ? 12 : 14)} y={y + (compact ? 34 : 60)} pills={a.pills} />
    </g>
  )
}

function Box({ c, at, x, y, w, h, title, id, center = true }: { c: Ctx; at: number; x: number; y: number; w: number; h: number; title: string; id: string; center?: boolean }) {
  const tx = center ? x + w / 2 : x + 14
  return (
    <g className={cls(c, at, at, 'node')}>
      <rect x={x} y={y} width={w} height={h} rx={12} />
      <text className="n-name" x={tx} y={y + h / 2 - 2} textAnchor={center ? 'middle' : 'start'}>
        {title}
      </text>
      <text className="n-id" x={tx} y={y + h / 2 + 14} textAnchor={center ? 'middle' : 'start'}>
        {id}
      </text>
    </g>
  )
}

function Person({ c, cx, top, label, labelAt }: { c: Ctx; cx: number; top: number; label: 'below' | 'right'; labelAt: Pt }) {
  const [lx, ly] = labelAt
  const anchor = label === 'below' ? 'middle' : 'start'
  return (
    <g className={cls(c, 5, 5, 'node person')}>
      <circle cx={cx} cy={top + 13} r={12} />
      <path d={`M${cx - 22} ${top + 54} C${cx - 22} ${top + 36} ${cx - 12} ${top + 30} ${cx} ${top + 30} C${cx + 12} ${top + 30} ${cx + 22} ${top + 36} ${cx + 22} ${top + 54} Z`} />
      <text className="n-name" x={lx} y={ly} textAnchor={anchor}>
        analista decide
      </text>
      <text className="n-id" x={lx} y={ly + 16} textAnchor={anchor}>
        decisão humana
      </text>
    </g>
  )
}

function Wide({ c }: { c: Ctx }) {
  const ay = [40, 186, 332]
  return (
    <svg className="diagram wide" viewBox="0 0 980 440" role="img" aria-label="Diagrama: demanda, orquestrador, três agentes, revisor e decisão humana">
      <g className={cls(c, 1, 1, 'node')}>
        <rect x={0} y={188} width={140} height={88} rx={12} />
        <text className="n-id" x={14} y={212}>
          demanda
        </text>
        <text className="n-big" x={14} y={240}>
          R$ 50 mi
        </text>
        <text className="n-sub" x={14} y={260}>
          custeio de soja
        </text>
      </g>
      <Edge c={c} at={2} d="M140 232 L186 232" tip={[186, 232]} from={[140, 232]} />
      <Box c={c} at={2} x={190} y={196} w={120} h={72} title="Orquestrador" id="orchestrator" />
      {ay.map((y, i) => (
        <Edge key={`o${i}`} c={c} at={2} d={`M310 232 C335 232 332 ${y + 46} 356 ${y + 46}`} tip={[356, y + 46]} from={[332, y + 46]} />
      ))}
      {AGENTS.map((a, i) => (
        <Agent key={a.id} c={c} a={a} x={360} y={ay[i]} w={250} h={92} />
      ))}
      {ay.map((y, i) => (
        <Edge key={`r${i}`} c={c} at={4} d={`M610 ${y + 46} C645 ${y + 46} 645 232 676 232`} tip={[676, 232]} from={[645, 232]} />
      ))}
      <Box c={c} at={4} x={680} y={196} w={140} h={72} title="Revisor" id="credit_review" />
      <Edge c={c} at={4} extra="loop" d="M750 196 C750 138 640 146 617 205" tip={[617, 205]} from={[640, 146]} />
      <text className={cls(c, 4, 4, 'loop-label')} x={700} y={134}>
        retrabalho
      </text>
      <Edge c={c} at={5} d="M820 232 L866 232" tip={[866, 232]} from={[820, 232]} />
      <Person c={c} cx={912} top={196} label="below" labelAt={[912, 280]} />
    </svg>
  )
}

function Tall({ c }: { c: Ctx }) {
  const ay = [150, 228, 306]
  return (
    <svg className="diagram tall" viewBox="0 0 360 560" role="img" aria-label="Diagrama: demanda, orquestrador, três agentes, revisor e decisão humana">
      <g className={cls(c, 1, 1, 'node')}>
        <rect x={20} y={2} width={320} height={50} rx={12} />
        <text className="n-id" x={34} y={31}>
          demanda
        </text>
        <text className="n-big" x={100} y={33}>
          R$ 50 mi
        </text>
        <text className="n-sub" x={184} y={32}>
          custeio de soja
        </text>
      </g>
      <Edge c={c} at={2} d="M180 52 L180 74" tip={[180, 74]} from={[180, 52]} />
      <Box c={c} at={2} x={110} y={78} w={140} h={48} title="Orquestrador" id="orchestrator" />
      <Edge c={c} at={2} d="M180 126 L180 140" tip={[180, 140]} from={[180, 126]} />
      <g className={cls(c, 2, -1, 'group')}>
        <rect x={30} y={142} width={300} height={240} rx={16} />
      </g>
      {AGENTS.map((a, i) => (
        <Agent key={a.id} c={c} a={a} x={44} y={ay[i]} w={272} h={66} compact />
      ))}
      <Edge c={c} at={4} d="M180 382 L180 402" tip={[180, 402]} from={[180, 382]} />
      <Box c={c} at={4} x={110} y={406} w={140} h={48} title="Revisor" id="credit_review" />
      <Edge c={c} at={4} extra="loop" d="M110 430 C40 430 14 420 14 390 L14 290 C14 268 22 261 40 261" tip={[40, 261]} from={[22, 261]} />
      <g transform="translate(10 372) rotate(-90)">
        <text className={cls(c, 4, 4, 'loop-label')}>retrabalho</text>
      </g>
      <Edge c={c} at={5} d="M180 454 L180 474" tip={[180, 474]} from={[180, 454]} />
      <Person c={c} cx={150} top={480} label="right" labelAt={[186, 508]} />
    </svg>
  )
}

function useScrollStep(count: number) {
  const refs = useRef<Array<HTMLElement | null>>([])
  const [step, setStep] = useState(1)
  useEffect(() => {
    let raf = 0
    const update = () => {
      raf = 0
      // a legenda vira ativa quando cruza uma linha um pouco abaixo do meio da tela
      const line = window.innerHeight * 0.55
      let s = 1
      refs.current.forEach((el, i) => {
        if (el && el.getBoundingClientRect().top < line) s = i + 1
      })
      setStep(Math.min(s, count))
    }
    const schedule = () => {
      if (!raf) raf = requestAnimationFrame(update)
    }
    schedule()
    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', schedule)
    }
  }, [count])
  return { step, refs }
}

export function HowItWorks() {
  const { step, refs } = useScrollStep(CAPTIONS.length)
  const [reduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const c: Ctx = { shown: reduced ? CAPTIONS.length : step, active: step }
  const lines = AUDIT.filter((l) => l.at <= c.shown)

  return (
    <section id="como-funciona" className="how" aria-labelledby="how-title">
      <header className="how-intro">
        <p className="how-kicker">como funciona</p>
        <h2 id="how-title">Da demanda à decisão, em cinco passos.</h2>
      </header>

      <ol className="how-steps">
        {CAPTIONS.map((text, i) => (
          <li
            key={text}
            ref={(el) => {
              refs.current[i] = el
            }}
            className={step === i + 1 ? 'act' : ''}
          >
            <span className="how-num">{pad(i + 1)}</span>
            <p>{text}</p>
          </li>
        ))}
      </ol>

      <div className="how-stage">
        {/* no celular as legendas viram espaçadores invisíveis e a ativa aparece aqui, junto do diagrama */}
        <p className="how-current" aria-hidden="true">
          <span className="how-num">{pad(step)}</span>
          {CAPTIONS[step - 1]}
        </p>
        <div className="how-figure">
          <Wide c={c} />
          <Tall c={c} />
        </div>
        <div className="audit" aria-label="Trilha de auditoria">
          <p className="audit-title">auditoria</p>
          <ol aria-live="off">
            {lines.map((l) => (
              <li key={`${l.at}-${l.who}-${l.what}`} className={`${l.tone ?? ''}${l.at === step ? ' new' : ''}`}>
                <span className="audit-step">{pad(l.at)}</span>
                <span>
                  {l.who} · {l.what}
                  {l.note && ` · ${l.note}`}
                </span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  )
}
