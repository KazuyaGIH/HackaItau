"""Protocolo de agente (ARCHITECTURE.md §5). Runtime comum em agents/runtime.py (S2.2)."""

from typing import Any, Protocol

from pydantic import BaseModel

from app.core.schemas.agent import AgentCard, AgentResult, TaskSpec
from app.core.schemas.context import ExecutionContext
from app.core.schemas.evidence import EvidenceBundle
from app.llm.provider import Message


class PromptParts(BaseModel):
    system: str
    user: str
    response_schema: str  # nome em OUTPUT_SCHEMAS

    def messages(self) -> list[Message]:
        return [Message(role="system", content=self.system), Message(role="user", content=self.user)]


class ToolboxLike(Protocol):
    """Interface que o código do agente usa na fase gather. Implementação: tools/gateway.py (S1.6)."""

    async def call(self, tool_name: str, **params: Any) -> Any: ...


class Agent(Protocol):
    card: AgentCard

    async def gather(self, ctx: ExecutionContext, task: TaskSpec, toolbox: ToolboxLike) -> EvidenceBundle:
        """CÓDIGO. Default do runtime: executa card.required_data. Risk adiciona baseline + cálculos."""
        ...

    def build_prompt(self, ctx: ExecutionContext, task: TaskSpec, evidence: EvidenceBundle) -> PromptParts: ...

    def validate(
        self, ctx: ExecutionContext, task: TaskSpec, raw_output: BaseModel, evidence: EvidenceBundle
    ) -> AgentResult:
        """CÓDIGO. Grounding, campos materiais copiados de CALC-*, regras do agente."""
        ...
