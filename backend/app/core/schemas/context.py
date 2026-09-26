"""Identidade, escopo e contexto de execução (ARCHITECTURE.md §7, §9).

Nenhum destes modelos é serializado para o prompt de um agente.
"""

from pydantic import BaseModel, ConfigDict, Field


class UserIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    name: str
    role: str
    # domínios de recurso legíveis pelo usuário (ex.: "client_financials"); carregado de identities.json, nunca do request
    permissions_read: tuple[str, ...]


class CaseScope(BaseModel):
    """Imutável após criação. Nenhum endpoint, tool ou parâmetro altera scope de case existente."""

    model_config = ConfigDict(frozen=True)

    client_ids: tuple[str, ...] = Field(min_length=1)
    purpose: str
    product_family: str | None = None


class ExecutionContext(BaseModel):
    """Contexto com que o backend autoriza cada tool call. case_scope é obrigatório: agentes nunca rodam sem scope."""

    model_config = ConfigDict(frozen=True)

    user: UserIdentity
    case_id: str
    task_id: str
    agent_id: str
    purpose: str
    case_scope: CaseScope
