"""Tool Registry, decisão de autorização e resultado de tool (ARCHITECTURE.md §7, §8)."""

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.schemas.evidence import CalculationRecord, SourceRecord

ToolKind = Literal["read", "search", "calc"]

# handler(params, deps) -> registros brutos (read/search) ou CalculationRecord (calc). `deps` é injetado pelo Gateway.
ToolHandler = Callable[[dict[str, Any], Any], Awaitable[list[dict[str, Any]] | CalculationRecord]]
ClientIdExtractor = Callable[[dict[str, Any]], list[str]]


def no_client_ids(_params: dict[str, Any]) -> list[str]:
    return []


def client_id_param(params: dict[str, Any]) -> list[str]:
    cid = params.get("client_id")
    return [cid] if cid else []


class ToolSpec(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str
    params_model: type[BaseModel]
    resource_domain: str
    kind: ToolKind
    handler: ToolHandler | None = None  # None no kernel; preenchido por S1/S2 no registro
    extract_client_ids: ClientIdExtractor = no_client_ids
    # como derivar resource_key para o evento/ID (ex.: "client_id", "commodity", "purpose", "query")
    key_param: str | None = None


class Decision(BaseModel):
    allowed: bool
    reason: str | None = None  # código curto; nunca detalhes de policy
    security: bool = False  # True → SECURITY_EVENT além de PERMISSION_DENIED
    row_scope: tuple[str, ...] = ()
    field_projection: list[str] | None = None  # None = sem projeção (dados sem campos por cliente); [] = nada
    never_fields: list[str] = Field(default_factory=list)

    @classmethod
    def deny(cls, reason: str, security: bool = False) -> "Decision":
        return cls(allowed=False, reason=reason, security=security)

    @classmethod
    def allow(cls, row_scope: tuple[str, ...], field_projection: list[str] | None, never_fields: list[str]) -> "Decision":
        return cls(allowed=True, row_scope=row_scope, field_projection=field_projection, never_fields=never_fields)


class ToolResult(BaseModel):
    ok: bool
    tool_name: str
    reason: str | None = None  # quando negado: {"error": "access_denied", "reason": code}
    sources: list[SourceRecord] = Field(default_factory=list)
    calculation: CalculationRecord | None = None

    @classmethod
    def denied(cls, tool_name: str, reason: str) -> "ToolResult":
        return cls(ok=False, tool_name=tool_name, reason=reason)

    @property
    def source_ids(self) -> list[str]:
        ids = [s.id for s in self.sources]
        if self.calculation:
            ids.append(self.calculation.id)
        return ids
