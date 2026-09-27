"""Protocolo de agente (ARCHITECTURE.md §5) + BaseAgent com gather/build_prompt padrão.

Runtime comum em agents/runtime.py. Um agente concreto sobrescreve só o que precisa.
"""

from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.config import APP_DIR
from app.core.schemas.agent import (
    CARRY_OVER_ACTION,
    HUMAN_ADJUSTMENT_ACTION,
    AgentCard,
    Assumption,
    ReworkInstruction,
    TaskSpec,
    ToolCallSpec,
)
from app.core.schemas.context import ExecutionContext
from app.core.schemas.evidence import EvidenceBundle
from app.core.schemas.outputs import OUTPUT_SCHEMAS
from app.core.schemas.tools import ToolResult
from app.llm.prompting import UNTRUSTED_RULES, render_evidence, render_schema, wrap_untrusted
from app.llm.provider import Message


class PromptParts(BaseModel):
    system: str
    user: str
    response_schema: str  # nome em OUTPUT_SCHEMAS

    def messages(self) -> list[Message]:
        return [Message(role="system", content=self.system), Message(role="user", content=self.user)]


class ToolboxLike(Protocol):
    """Interface que o código do agente usa na fase gather. Implementação: tools/gateway.py (S1.6)."""

    async def call(self, tool_name: str, **params: Any) -> ToolResult: ...


class OutputValidationError(Exception):
    """Agent.validate rejeitou a saída do LLM. O runtime devolve os problemas ao modelo uma vez; depois falha auditado."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


class ValidatedOutput(BaseModel):
    """Retorno de Agent.validate. O runtime completa usage, output_id, evidence_ids e registra OUT-*."""

    output: dict[str, Any]
    assumptions: list[Assumption] = Field(default_factory=list)
    calculation_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Agent(Protocol):
    card: AgentCard

    async def gather(self, ctx: ExecutionContext, task: TaskSpec, toolbox: ToolboxLike) -> EvidenceBundle:
        """CÓDIGO. Default do runtime: executa card.required_data. Risk adiciona baseline + cálculos."""
        ...

    def build_prompt(self, ctx: ExecutionContext, task: TaskSpec, evidence: EvidenceBundle) -> PromptParts: ...

    def validate(
        self, ctx: ExecutionContext, task: TaskSpec, raw_output: BaseModel, evidence: EvidenceBundle
    ) -> ValidatedOutput:
        """CÓDIGO. Grounding, campos materiais copiados de CALC-*, regras do agente."""
        ...


def resolve_params(spec: ToolCallSpec, ctx: ExecutionContext, task: TaskSpec) -> dict[str, Any]:
    """params_from: "scope.client_id" | "task.inputs.<campo>". Nunca lê do LLM."""
    params = dict(spec.params)
    for name, path in spec.params_from.items():
        if path == "scope.client_id":
            params[name] = ctx.case_scope.client_ids[0]
        elif path.startswith("task.inputs."):
            params[name] = task.inputs.get(path[len("task.inputs.") :])
        else:
            raise ValueError(f"params_from desconhecido: {path}")
    return params


async def gather_required_data(
    card: AgentCard, ctx: ExecutionContext, task: TaskSpec, toolbox: ToolboxLike
) -> EvidenceBundle:
    bundle = EvidenceBundle()
    for spec in card.required_data:
        params = resolve_params(spec, ctx, task)
        if any(v is None for v in params.values()):
            bundle.denied.append(f"{spec.tool}:missing_param")
            continue
        result = await toolbox.call(spec.tool, **params)
        if not result.ok:
            bundle.denied.append(f"{spec.tool}:{result.reason}")
            continue
        bundle.sources.extend(result.sources)
        if result.calculation is not None:
            bundle.calculations.append(result.calculation)
    return bundle


def _rework_section(rework: ReworkInstruction) -> str:
    """Seção de rework do prompt. O texto (finding ou comentário do analista) entra sempre como untrusted_data."""
    action = f"Ação requerida (backend): {rework.required_action} {rework.params}"
    if rework.required_action == CARRY_OVER_ACTION:
        return f"## Parâmetros de rodadas anteriores (backend)\n{action}"
    if rework.required_action == HUMAN_ADJUSTMENT_ACTION:
        return (
            "## Ajuste solicitado pelo analista (humano)\n"
            "Revise seu resultado considerando o comentário abaixo, sem sair das evidências e dos cálculos citados.\n"
            f"{action}\n" + wrap_untrusted("analyst_comment", rework.message)
        )
    return f"## Rework solicitado pelo Review\n{action}\n" + wrap_untrusted("review_finding", rework.message)


class BaseAgent:
    card: AgentCard

    def __init__(self, card: AgentCard) -> None:
        self.card = card
        self._playbook = (APP_DIR / card.playbook_path).read_text(encoding="utf-8")

    @property
    def playbook(self) -> str:
        return self._playbook

    async def gather(self, ctx: ExecutionContext, task: TaskSpec, toolbox: ToolboxLike) -> EvidenceBundle:
        return await gather_required_data(self.card, ctx, task, toolbox)

    def build_prompt(self, ctx: ExecutionContext, task: TaskSpec, evidence: EvidenceBundle) -> PromptParts:
        card = self.card
        system = "\n\n".join(
            [
                f"# {card.name} (v{card.version})\n{card.description}",
                "Ações proibidas: " + ", ".join(card.forbidden_actions) + ".",
                self._playbook,
                UNTRUSTED_RULES,
            ]
        )
        sections = [f"## Tarefa\n{task.instruction}"]
        if task.inputs:
            sections.append("## Inputs (projeção de resultados anteriores)\n" + wrap_untrusted("task_inputs", task.inputs))
        if task.rework is not None:
            sections.append(_rework_section(task.rework))
        sections.append("## Evidências disponíveis\n" + (render_evidence(evidence) or "(nenhuma)"))
        sections.append(
            "## IDs autorizados para citação (lista fechada do backend)\n"
            + ", ".join(sorted(evidence.allowed_ids()))
            + "\nPara citar a análise de outro agente, use o OUT-* listado. Referências internas a esse resultado "
            "não autorizam citar SRC/KB/CALC que não estejam nesta lista. Não abrevie nem invente IDs."
        )
        sections.append(
            "## Formato de saída\nResponda apenas com JSON válido conforme este schema:\n"
            + render_schema(OUTPUT_SCHEMAS[card.output_schema])
        )
        return PromptParts(system=system, user="\n\n".join(sections), response_schema=card.output_schema)

    def validate(
        self, ctx: ExecutionContext, task: TaskSpec, raw_output: BaseModel, evidence: EvidenceBundle
    ) -> ValidatedOutput:
        return ValidatedOutput(output=raw_output.model_dump())
