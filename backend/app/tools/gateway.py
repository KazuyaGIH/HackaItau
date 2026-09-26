"""Tool / Data Gateway (ARCHITECTURE.md §8). Única API que código de agente usa para tocar dados/cálculos.

Ordem fixa em `call`: validação de params → authorize → eventos → handler → row scope → field projection →
injection guard (+ scope probe) → registro de evidência → TOOL_CALLED.
"""

from typing import Any

from pydantic import ValidationError

from app.core.events import EventLog
from app.core.evidence import EvidenceRegistry
from app.core.schemas.agent import AgentCard
from app.core.schemas.context import ExecutionContext
from app.core.schemas.events import EventType, SecurityEventKind, ToolEventPayload
from app.core.schemas.evidence import CalculationRecord, SourceRecord, knowledge_id, source_id
from app.core.schemas.tools import Decision, ToolResult, ToolSpec
from app.governance.filters import apply_field_projection, apply_row_scope
from app.governance.injection_guard import scan_record
from app.governance.policy_engine import authorize
from app.tools.deps import ToolDeps
from app.tools.registry import TOOL_REGISTRY

REASON_UNKNOWN_TOOL = "unknown_tool"
REASON_INVALID_PARAMS = "invalid_params"
REASON_NO_HANDLER = "tool_handler_not_installed"

# campo que identifica o registro dentro do domínio (para SRC-<DOMAIN>-<KEY> determinístico)
_RECORD_KEY_FIELD = {"documents": "doc_id", "product_catalog": "product_id", "market_data": "commodity"}
_PROBE_TOOL = "get_client_profile"


class Toolbox:
    def __init__(
        self,
        ctx: ExecutionContext,
        card: AgentCard,
        deps: ToolDeps,
        events: EventLog,
        evidence: EvidenceRegistry,
        *,
        registry: dict[str, ToolSpec] | None = None,
    ) -> None:
        self.ctx = ctx
        self.card = card
        self.deps = deps
        self.events = events
        self.evidence = evidence
        self._registry = registry if registry is not None else TOOL_REGISTRY

    # ------------------------------------------------------------------ public

    async def call(self, tool_name: str, **params: Any) -> ToolResult:
        spec = self._registry.get(tool_name)
        if spec is None:
            self._emit_denied(tool_name, "unknown", None, Decision.deny(REASON_UNKNOWN_TOOL))
            return ToolResult.denied(tool_name, REASON_UNKNOWN_TOOL)

        resource_key = str(params.get(spec.key_param)) if spec.key_param and spec.key_param in params else None
        try:
            spec.params_model(**params)
        except ValidationError:
            self._emit_denied(spec.name, spec.resource_domain, resource_key, Decision.deny(REASON_INVALID_PARAMS))
            return ToolResult.denied(spec.name, REASON_INVALID_PARAMS)

        decision = authorize(self.ctx, self.card, spec, params)
        self._emit_checked(spec, resource_key, decision)
        if not decision.allowed:
            self._emit_denied(spec.name, spec.resource_domain, resource_key, decision)
            return ToolResult.denied(spec.name, decision.reason or "denied")

        if spec.handler is None:
            self._emit_denied(spec.name, spec.resource_domain, resource_key, Decision.deny(REASON_NO_HANDLER))
            return ToolResult.denied(spec.name, REASON_NO_HANDLER)

        raw = await spec.handler(params, self.deps)

        if isinstance(raw, CalculationRecord):
            self.evidence.register(raw)
            self._emit_called(spec, resource_key, [raw.id], fields_hidden=0)
            return ToolResult(ok=True, tool_name=spec.name, calculation=raw)

        sources = self._filter_and_register(spec, params, resource_key, raw, decision)
        hidden = sum(s.fields_hidden for s in sources)
        self._emit_called(spec, resource_key, [s.id for s in sources], fields_hidden=hidden)
        return ToolResult(ok=True, tool_name=spec.name, sources=sources)

    def probe(self, client_id: str, via_tool: str | None = None) -> Decision:
        """Scope probe (§11.4): avalia a Policy Engine contra o alvo citado, sem executar handler. Sempre auditado."""
        spec = self._probe_spec(via_tool)
        decision = authorize(self.ctx, self.card, spec, {"client_id": client_id})
        payload = self._payload(spec.name, spec.resource_domain, client_id, decision, probe=True)
        self.events.emit(EventType.PERMISSION_CHECKED, payload, agent_id=self.ctx.agent_id, task_id=self.ctx.task_id)
        if not decision.allowed:
            self.events.emit(EventType.PERMISSION_DENIED, payload, agent_id=self.ctx.agent_id, task_id=self.ctx.task_id)
            self.events.emit(
                EventType.SECURITY_EVENT,
                {
                    "kind": SecurityEventKind.SCOPE_VIOLATION_BLOCKED.value,
                    "probe": True,
                    "target_client_id": client_id,
                    "reason": decision.reason,
                    "permissions_changed": False,
                },
                agent_id=self.ctx.agent_id,
                task_id=self.ctx.task_id,
            )
        return decision

    # ----------------------------------------------------------------- private

    def _probe_spec(self, via_tool: str | None) -> ToolSpec:
        """Prefere uma tool do próprio card que receba client_id, para o deny cair na regra de scope."""
        candidates = [via_tool] if via_tool else []
        candidates += list(self.card.tools) + [_PROBE_TOOL]
        for name in candidates:
            spec = self._registry.get(name)
            if spec is not None and spec.extract_client_ids({"client_id": "PROBE"}):
                return spec
        return self._registry[_PROBE_TOOL]

    def _filter_and_register(
        self,
        spec: ToolSpec,
        params: dict[str, Any],
        resource_key: str | None,
        raw: list[dict[str, Any]],
        decision: Decision,
    ) -> list[SourceRecord]:
        in_scope = apply_row_scope(raw, decision.row_scope)
        sources: list[SourceRecord] = []
        for record in in_scope:
            projected, hidden = apply_field_projection(record, decision.field_projection, decision.never_fields)
            if not projected:
                continue  # deny por omissão: sem projeção para o agente, nada chega
            scan = scan_record(projected, self.ctx.case_scope)
            rec_id, title = self._identify(spec, params, resource_key, record)
            source = SourceRecord(
                id=rec_id,
                kind="knowledge" if spec.kind == "search" else "source",
                resource_domain=spec.resource_domain,
                resource_key=str(record.get(_RECORD_KEY_FIELD.get(spec.resource_domain, ""), resource_key or "")),
                data=projected,
                mock=True,
                accessed_by_agent=self.ctx.agent_id,
                fields_hidden=hidden,
                flagged=scan.flagged,
                out_of_scope_refs=scan.out_of_scope_refs,
                title=title,
            )
            self.evidence.register(source)
            sources.append(source)
            if scan.flagged:
                self.events.emit(
                    EventType.SECURITY_EVENT,
                    {
                        "kind": SecurityEventKind.INJECTION_SUSPECTED.value,
                        "source_id": source.id,
                        "resource_domain": spec.resource_domain,
                        "out_of_scope_refs": scan.out_of_scope_refs,
                        "patterns_matched": len(scan.matched_patterns),
                        "blocked": False,
                        "permissions_changed": False,
                    },
                    agent_id=self.ctx.agent_id,
                    task_id=self.ctx.task_id,
                )
                for ref in scan.out_of_scope_refs:
                    self.probe(ref, via_tool=spec.name)
        return sources

    @staticmethod
    def _identify(
        spec: ToolSpec, params: dict[str, Any], resource_key: str | None, record: dict[str, Any]
    ) -> tuple[str, str | None]:
        if spec.kind == "search":
            return knowledge_id(record["doc_id"], int(record["chunk_index"])), record.get("title")
        key_field = _RECORD_KEY_FIELD.get(spec.resource_domain)
        key = str(record.get(key_field) if key_field else (record.get("client_id") or resource_key or "GLOBAL"))
        return source_id(spec.resource_domain, key.upper()), record.get("title") or record.get("name")

    def _payload(
        self,
        action: str,
        domain: str,
        resource_key: str | None,
        decision: Decision,
        *,
        probe: bool = False,
        source_ids: list[str] | None = None,
        fields_hidden: int = 0,
    ) -> dict[str, Any]:
        return ToolEventPayload(
            action=action,
            resource_domain=domain,
            resource_key=resource_key,
            allowed=decision.allowed,
            reason=decision.reason,
            purpose=self.ctx.purpose,
            source_ids=source_ids or [],
            fields_hidden=fields_hidden,
            probe=probe,
        ).model_dump()

    def _emit_checked(self, spec: ToolSpec, resource_key: str | None, decision: Decision) -> None:
        self.events.emit(
            EventType.PERMISSION_CHECKED,
            self._payload(spec.name, spec.resource_domain, resource_key, decision),
            agent_id=self.ctx.agent_id,
            task_id=self.ctx.task_id,
        )

    def _emit_denied(self, action: str, domain: str, resource_key: str | None, decision: Decision) -> None:
        payload = self._payload(action, domain, resource_key, decision)
        self.events.emit(EventType.PERMISSION_DENIED, payload, agent_id=self.ctx.agent_id, task_id=self.ctx.task_id)
        if decision.security:
            self.events.emit(
                EventType.SECURITY_EVENT,
                {
                    "kind": SecurityEventKind.SCOPE_VIOLATION_BLOCKED.value,
                    "probe": False,
                    "action": action,
                    "target_client_id": resource_key,
                    "reason": decision.reason,
                    "permissions_changed": False,
                },
                agent_id=self.ctx.agent_id,
                task_id=self.ctx.task_id,
            )

    def _emit_called(self, spec: ToolSpec, resource_key: str | None, source_ids: list[str], *, fields_hidden: int) -> None:
        self.events.emit(
            EventType.TOOL_CALLED,
            self._payload(
                spec.name,
                spec.resource_domain,
                resource_key,
                Decision.allow((), None, []),
                source_ids=source_ids,
                fields_hidden=fields_hidden,
            ),
            agent_id=self.ctx.agent_id,
            task_id=self.ctx.task_id,
        )
