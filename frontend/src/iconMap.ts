// Ícones (lucide) por agente e por tipo de passo. Mantidos fora dos componentes para reuso.
import {
  Ban,
  BookOpen,
  Bot,
  Calculator,
  CircleCheck,
  CircleX,
  CornerUpLeft,
  Database,
  Gauge,
  Layers,
  ListChecks,
  Play,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  type LucideIcon,
} from 'lucide-react'
import { ELIGIBILITY, REVIEW, RISK, STRUCTURING, type StepKind } from './squad'

const AGENT_ICON: Record<string, LucideIcon> = {
  [ELIGIBILITY]: ListChecks,
  [RISK]: Gauge,
  [STRUCTURING]: Layers,
  [REVIEW]: ShieldCheck,
}

export const agentIcon = (id: string): LucideIcon => AGENT_ICON[id] ?? Bot

export const STEP_ICON: Record<StepKind, LucideIcon> = {
  start: Play,
  data: Database,
  calc: Calculator,
  policy: BookOpen,
  llm: Sparkles,
  denied: Ban,
  security: ShieldAlert,
  rejected: TriangleAlert,
  reopen: CornerUpLeft,
  finding: TriangleAlert,
  done: CircleCheck,
  fail: CircleX,
}
