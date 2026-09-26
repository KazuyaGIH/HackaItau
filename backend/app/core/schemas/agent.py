"""Contrato base de um agente (ARCHITECTURE.md §5)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

AssumptionOrigin = Literal["code", "llm_qualitative"]


class ToolCallSpec(BaseModel):
    """Uma tool call FIXA executada por código na fase gather. Parâmetros nunca vêm do LLM.

    `params` são literais; `params_from` mapeia nome do parâmetro → caminho em {"scope", "task"}
    (ex.: {"client_id": "scope.client_id", "commodity": "task.inputs.crop"}).
    """

    tool: str
    params: dict[str, Any] = Field(default_factory=dict)
    params_from: dict[str, str] = Field(default_factory=dict)


class AgentCard(BaseModel):
    agent_id: str
    name: str
    version: str
    description: str = ""
    capabilities: list[str]
    tools: list[str]  # ALLOWLIST — únicas tools que o código deste agente pode invocar via Gateway
    allowed_data_domains: list[str]
    required_data: list[ToolCallSpec] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    output_schema: str
    playbook_path: str
    model_role: Literal["default"] = "default"  # P0: um único modelo; P1: fast/strong


class ReworkInstruction(BaseModel):
    finding_ids: list[str]
    required_action: str  # chave em review/remediations.py
    params: dict[str, Any] = Field(default_factory=dict)  # ex.: {"baseline_policy": "historical"}
    message: str  # texto do finding; entra no prompt como untrusted_data


class TaskSpec(BaseModel):
    task_id: str
    agent_id: str
    round: int = 1
    instruction: str  # TRUSTED: template escrito pelo Orchestrator
    inputs: dict[str, Any] = Field(default_factory=dict)  # projeção compacta de outputs upstream (plans.input_projection)
    upstream_output_ids: list[str] = Field(default_factory=list)  # OUT-* citáveis
    rework: ReworkInstruction | None = None


class Assumption(BaseModel):
    name: str
    value: Any
    unit: str | None = None
    source_id: str | None = None
    justification: str = ""
    origin: AssumptionOrigin


class LLMUsage(BaseModel):
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    retries: int = 0


class AgentResult(BaseModel):
    agent_id: str
    task_id: str
    round: int
    output: dict[str, Any]  # instância validada do output_schema (dump)
    output_id: str  # OUT-<agent_id>-R<n>
    evidence_ids: list[str] = Field(default_factory=list)
    calculation_ids: list[str] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    usage: LLMUsage
    warnings: list[str] = Field(default_factory=list)
    data_domains_accessed: list[str] = Field(default_factory=list)
    tool_calls: int = 0
