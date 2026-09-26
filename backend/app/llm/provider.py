"""Abstração mínima de provider LLM (ARCHITECTURE.md §19.4). P0: um provider OpenAI-compatible, sem tools."""

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.core.schemas.agent import LLMUsage


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ToolSchema(BaseModel):
    """Reservado para P1 (tool-calling dinâmico). Não usado no P0."""

    name: str
    description: str
    parameters: dict[str, Any]


class ToolCall(BaseModel):
    """Reservado para P1."""

    id: str
    name: str
    arguments: dict[str, Any]


class LLMResponse(BaseModel):
    content: str | None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: LLMUsage


class LLMProvider(Protocol):
    async def complete(
        self,
        *,
        model: str,
        messages: list[Message],
        response_schema: type[BaseModel] | None = None,
        temperature: float = 0.0,
        tools: list[ToolSchema] | None = None,  # P1
    ) -> LLMResponse: ...
