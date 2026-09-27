// Espelho TS dos contratos do kernel (backend/app/core/schemas). Mantido à mão no P0 — sem codegen.

export interface HealthResponse {
  ok: boolean
  llm_mode: 'real' | 'unconfigured'
  demo_mode: boolean
}

// identidade fictícia da demo (backend: governance/identities.json)
export interface Identity {
  user_id: string
  name: string
  role: string
  permissions_read: string[]
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
  | 'GROUNDING_REJECTED'
  | 'OUTPUT_REJECTED'
  | 'AGENT_COMPLETED'
  | 'DOCUMENT_ATTACHED'
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
  // request_adjustment + target_agent: o backend reabre esse agente (e dependentes) com o comentário
  target_agent?: string
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
  request_kind: string | null
  tenor_months: number | null
  guarantees: string[]
  region: string | null
  area_hectares: number | null
}

export interface OpenQuestion {
  key: string
  question: string
  blocking: boolean
}

export interface AttachmentView {
  doc_id: string
  filename: string
  doc_type: string
  size_bytes: number
  chars: number
  truncated: boolean
  flagged: boolean
  uploaded_at: string
}

export interface Citation {
  id: string
  title: string
  excerpt: string
}

export type AssistKind =
  | 'credit_demand'
  | 'case_reply'
  | 'adjustment'
  | 'case_question'
  | 'policy_answer'
  | 'capabilities'
  | 'out_of_scope'
  | 'clarify'

export interface AssistReply {
  kind: AssistKind
  message: string
  bullets: string[]
  citations: Citation[]
  suggestions: string[]
}

export interface AgentMetrics {
  agent_id: string
  name: string
  version: string
  description: string
  capabilities: string[]
  tools: string[]
  data_domains: string[]
  forbidden_actions: string[]
  runs: number
  completed: number
  failed: number
  in_progress: number
  completion_pct: number | null
  validation_clean: number
  validation_first_pass_pct: number | null
  hits: number
  validator_fixes: number
  reopened_by_review: number
  adjusted_by_human: number
  errors: number
  accuracy_pct: number | null
  findings_owned: number
  tool_calls: number
  denied_calls: number
  llm_calls: number
  tokens_in: number
  tokens_out: number
  avg_context_tokens: number
  avg_latency_ms: number | null
  reviewer: {
    findings_raised: number
    material_findings: number
    reworks_triggered: number
    confirmed_by_rework: number
    confirmation_pct: number | null
  } | null
}

export interface Metrics {
  cases: number
  reports: number
  human_decisions: number
  tokens: { input: number; output: number }
  context: {
    squad_tokens: number
    squad_calls: number
    generalist_tokens: number
    generalist_calls: number
    saved_tokens: number
    saved_pct: number | null
    per_call_squad: number
    per_call_generalist: number
    per_call_saved_pct: number | null
  }
  agents: AgentMetrics[]
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
  policy_limits?: {
    source_doc_id: string
    coverage_comfortable_min: number | null
    coverage_reduced_buffer_min: number | null
    coverage_attention_required_min: number | null
    net_debt_ebitda_max: number | null
    pro_forma_leverage_max: number | null
  }
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
  llm_mode: 'real' | 'unconfigured'
  error: string | null
  last_event_seq: number
  open_questions: OpenQuestion[]
  attachments: AttachmentView[]
  analyst_context: Record<string, string>
}
export interface BenchmarkSummary {
  published_snapshot?: boolean
  version: number
  run_id: string
  created_at: string
  status: 'complete' | 'partial'
  planned_runs: number
  completed_runs: number
  quality_status: 'reviewed' | 'pending_human_review'
  conclusion: string
  groups: {
    architecture: 'squad' | 'generalist'
    model_label: string
    model: string
    reasoning_effort?: string | null
    runs: number
    automatic_passes: number
    errors: number
    reviewed: number
    accepted: number | null
    accepted_rate: number | null
    accepted_rate_ci95: [number, number] | null
    calls: number
    tokens_in: number
    tokens_out: number
    usage_complete: boolean
    total_cost_usd: number | null
    cost_per_accepted_usd: number | null
    mean_latency_seconds: number
  }[]
}
