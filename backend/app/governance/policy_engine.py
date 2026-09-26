"""Policy Engine (ARCHITECTURE.md §7): função pura, sem LLM, sem I/O.

Acesso efetivo = user ∩ agent ∩ purpose ∩ case_scope ∩ resource_policy. Nunca união.
Deny devolve só um código; nunca detalhes de policy.
"""

from collections.abc import Mapping
from typing import Any

from app.core.schemas.agent import AgentCard
from app.core.schemas.context import ExecutionContext
from app.core.schemas.tools import Decision, ToolSpec
from app.governance.loader import PurposeSpec, ResourcePolicy, load_purposes, load_resource_policies

REASON_TOOL_NOT_ALLOWED = "tool_not_allowed_for_agent"
REASON_USER = "resource_not_authorized_for_user"
REASON_AGENT = "resource_not_authorized_for_agent"
REASON_PURPOSE = "resource_not_authorized_for_purpose"
REASON_UNKNOWN_PURPOSE = "unknown_purpose"
REASON_PURPOSE_MISMATCH = "purpose_mismatch_with_scope"
REASON_SCOPE = "client_out_of_case_scope"
REASON_NO_POLICY = "no_resource_policy"


def authorize(
    ctx: ExecutionContext,
    card: AgentCard,
    tool: ToolSpec,
    params: Mapping[str, Any],
    *,
    purposes: Mapping[str, PurposeSpec] | None = None,
    policies: Mapping[str, ResourcePolicy] | None = None,
) -> Decision:
    purposes = purposes if purposes is not None else load_purposes()
    policies = policies if policies is not None else load_resource_policies()

    if tool.name not in card.tools:
        return Decision.deny(REASON_TOOL_NOT_ALLOWED)

    domain = tool.resource_domain
    if domain not in ctx.user.permissions_read:
        return Decision.deny(REASON_USER)
    if domain not in card.allowed_data_domains:
        return Decision.deny(REASON_AGENT)
    if ctx.purpose != ctx.case_scope.purpose:
        return Decision.deny(REASON_PURPOSE_MISMATCH)
    purpose = purposes.get(ctx.purpose)
    if purpose is None:
        return Decision.deny(REASON_UNKNOWN_PURPOSE)
    if domain not in purpose.allowed_data_domains:
        return Decision.deny(REASON_PURPOSE)

    for cid in tool.extract_client_ids(dict(params)):
        if cid not in ctx.case_scope.client_ids:
            return Decision.deny(REASON_SCOPE, security=True)

    policy = policies.get(domain)
    if policy is None:
        return Decision.deny(REASON_NO_POLICY)

    fields = policy.fields_for(card.agent_id)
    projection: list[str] | None
    if fields is None:
        projection = []  # sem entrada para o agente → deny por omissão (nada é retornado)
    elif fields == ["*"]:
        projection = None  # todos os campos, menos `never`
    else:
        projection = list(fields)

    # row_scope vale para qualquer domínio: registro com client_id fora do scope nunca passa, mesmo em domínio "none"
    return Decision.allow(row_scope=ctx.case_scope.client_ids, field_projection=projection, never_fields=list(policy.never))
