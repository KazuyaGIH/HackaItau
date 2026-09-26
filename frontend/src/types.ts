// Espelho TS dos contratos do kernel (backend/app/core/schemas). Mantido à mão no P0 — sem codegen.

export interface HealthResponse {
  ok: boolean
  llm_mode: 'real' | 'fallback' | 'unconfigured'
  demo_mode: boolean
}

export type CaseStatus =
  | 'created'
  | 'interpreting'
  | 'waiting_input'
  | 'planned'
  | 'running'
  | 'reviewing'
  | 'consolidating'
  | 'human_review_required'
  | 'completed_demo'
  | 'failed'

export type AgentStatus = 'selected' | 'waiting' | 'running' | 'completed' | 'reopened' | 'blocked' | 'failed'

export type Severity = 'info' | 'low' | 'medium' | 'high'

export type EventType =
  | 'CASE_CREATED'
  | 'ORCHESTRATOR_STARTED'
  | 'BOOTSTRAP_RESOLVED'
  | 'MISSING_INFO_REQUESTED'
  | 'INPUT_RECEIVED'
  | 'SCOPE_FROZEN'
  | 'AGENT_SELECTED'
  | 'AGENT_STARTED'
  | 'PERMISSION_CHECKED'
  | 'PERMISSION_DENIED'
  | 'SECURITY_EVENT'
  | 'TOOL_CALLED'
  | 'LLM_CALLED'
  | 'LLM_FALLBACK_USED'
  | 'GROUNDING_REJECTED'
  | 'AGENT_COMPLETED'
  | 'REVIEW_STARTED'
  | 'REVIEW_ISSUE_FOUND'
  | 'REVIEW_COMPLETED'
  | 'TASK_REOPENED'
  | 'RESULT_CONSOLIDATED'
  | 'OUTPUT_GUARD_APPLIED'
  | 'HUMAN_REVIEW_REQUIRED'
  | 'HUMAN_APPROVED'
  | 'HUMAN_ADJUSTMENT_REQUESTED'
  | 'CASE_COMPLETED'
  | 'EXECUTION_FAILED'

export interface CaseEvent {
  seq: number
  ts: string
  case_id: string
  type: EventType
  agent_id: string | null
  task_id: string | null
  payload: Record<string, unknown>
  audit: boolean
}

export interface DemoOptions {
  adversarial_document: boolean
}

export interface CreateCaseRequest {
  user_id: string
  prompt: string
  demo_options: DemoOptions
}

export interface InputRequest {
  answers: Record<string, unknown>
}

export interface HumanReviewRequest {
  decision: 'approve_next_step' | 'request_adjustment'
  comment: string
}

export interface CaseScope {
  client_ids: string[]
  purpose: string
  product_family: string | null
}

export interface InterpretedDemand {
  intent: string
  client_ref: string | null
  requested_amount: number | null
  purpose: string | null
  crop: string | null
  cycle: string | null
  notes: string
}

export interface MissingInfoRequest {
  reason: string
  items: string[]
  message: string
}

export interface AgentCardState {
  agent_id: string
  name: string
  status: AgentStatus
  round: number
  summary: string
  data_domains_accessed: string[]
  tool_calls: number
  source_count: number
  denied_calls: number
  fallback_used: boolean
  output: Record<string, unknown> | null
}

export interface CaseCounters {
  tool_calls: number
  sources: number
  permission_checks: number
  permission_denials: number
  security_events: number
  llm_calls: number
  tokens_in: number
  tokens_out: number
  elapsed_ms: number
}

export interface Finding {
  id: string
  code: string
  severity: Severity
  message: string
  owner_agent: string | null
  evidence_ids: string[]
  origin: 'validator' | 'ai_review' | 'output_guard'
  required_action: string | null
  status: 'open' | 'resolved' | 'informational'
}

export interface ReviewOutput {
  review_status: 'passed' | 'passed_with_findings' | 'rework_required'
  findings: Finding[]
  grounding_ok: boolean
  policy_ok: boolean
  reexecution_required: boolean
  reopen_agent: string | null
  rework_round: number
  overall_assessment: string
}

export interface ReportItem {
  text: string
  evidence_ids: string[]
  severity: Severity | null
  code: string | null
}

export interface CalculationView {
  calculation_id: string
  name: string
  formula: string
  inputs: Record<string, unknown>
  input_sources: Record<string, string>
  outputs: Record<string, unknown>
  classification: string | null
  thresholds_source_ids: string[]
}

export interface AssumptionView {
  name: string
  value: unknown
  unit: string | null
  source_id: string | null
  origin: 'code' | 'llm_qualitative'
  justification: string
  changed_in_rework: boolean
  previous_value: unknown
}

export interface ScenarioView {
  scenario_id: string
  label: string
  shocks: Record<string, number>
  coverage: number
  expected_cash_generation: number
  classification: 'comfortable' | 'reduced_buffer' | 'attention_required' | 'insufficient'
  calculation_id: string
}

export interface Alternative {
  id: string
  name: string
  product_id: string
  amount: number
  tenor_months: number
  amortization: string
  guarantees: string[]
  conditions: string[]
  rationale: string
  when_it_fits: string
  advantages: string[]
  risks: string[]
  trade_offs: string[]
  addressed_risk_codes: string[]
  evidence_ids: string[]
}

export interface EvidenceRef {
  id: string
  kind: 'source' | 'knowledge' | 'calculation' | 'agent_output'
  label: string
  agent_id: string | null
  mock: boolean
}

export interface SourceRecord {
  id: string
  kind: 'source' | 'knowledge'
  resource_domain: string
  resource_key: string
  data: Record<string, unknown>
  mock: boolean
  accessed_by_agent: string
  fields_hidden: number
  flagged: boolean
  out_of_scope_refs: string[]
  title: string | null
}

export interface CalculationRecord {
  id: string
  kind: 'calculation'
  name: string
  formula: string
  inputs: Record<string, unknown>
  input_sources: Record<string, string>
  thresholds_source_ids: string[]
  outputs: Record<string, unknown>
  classification: string | null
  computed_by_agent: string
  round: number
}

export interface AgentOutputRecord {
  id: string
  kind: 'agent_output'
  agent_id: string
  round: number
  output: Record<string, unknown>
}

export type EvidenceItem = SourceRecord | CalculationRecord | AgentOutputRecord

export interface AgentGovernanceView {
  agent_id: string
  data_domains_accessed: string[]
  tool_calls: number
  denied_calls: number
  fields_hidden: number
  llm_calls: number
  fallback_used: boolean
}

export interface GovernanceView {
  user_id: string
  purpose: string
  case_scope_client_ids: string[]
  agents: AgentGovernanceView[]
  permission_denials: number
  security_events: number
  fields_hidden_total: number
  permissions_changed: false
}

export interface HumanGateView {
  status: 'pending' | 'approved_next_step' | 'adjustment_requested'
  available_actions: Array<'approve_next_step' | 'request_adjustment'>
  comments: string[]
  notice: string
}

export interface Report {
  case_id: string
  client_id: string
  generated_at: string
  decision_status: 'ready_for_human_review'
  disclaimer: string
  summary: {
    objective: string
    requested_amount: number | null
    purpose: string | null
    crop: string | null
    eligibility_status: string
    alternatives_count: number
    rework_rounds: number
  }
  facts: ReportItem[]
  calculations: CalculationView[]
  assumptions: AssumptionView[]
  favorable_factors: ReportItem[]
  risk_factors: ReportItem[]
  stress_scenarios: ScenarioView[]
  uncertainties: ReportItem[]
  missing_data: ReportItem[]
  alternatives: Alternative[]
  sources: EvidenceRef[]
  review: {
    review_status: string
    findings: Finding[]
    rework_rounds: number
    resolved_count: number
    open_count: number
    overall_assessment: string
  }
  governance: GovernanceView
  human_gate: HumanGateView
  llm_mode: 'real' | 'fallback' | 'mixed'
}

export interface CaseState {
  case_id: string
  status: CaseStatus
  user_id: string
  prompt: string
  demo_options: DemoOptions
  created_at: string
  updated_at: string
  interpreted: InterpretedDemand | null
  scope: CaseScope | null
  selected_agents: string[]
  agents: AgentCardState[]
  missing_info: MissingInfoRequest | null
  review: ReviewOutput | null
  rework_rounds: number
  report: Report | null
  counters: CaseCounters
  llm_mode: string
  error: string | null
  last_event_seq: number
}
