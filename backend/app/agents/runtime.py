"""Runtime comum dos agentes (ARCHITECTURE.md §5): gather (código) → reason (1 chamada LLM, sem tools) → validate (código).

O LLM só vê o EvidenceBundle; só o runtime cria OUT-*; IDs não fornecidos ao agente são removidos (GROUNDING_REJECTED).
"""

import json
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from app.agents.base import Agent, OutputValidationError, ValidatedOutput
from app.core.events import EventLog
from app.core.evidence import EvidenceRegistry
from app.core.schemas.agent import AgentResult, LLMUsage, TaskSpec
from app.core.schemas.context import ExecutionContext
from app.core.schemas.events import EventType
from app.core.schemas.evidence import AgentOutputRecord, output_id
from app.core.schemas.outputs import OUTPUT_SCHEMAS
from app.llm.openai_compat import LLMError
from app.llm.prompting import extract_json
from app.llm.provider import LLMProvider, Message
from app.tools.gateway import Toolbox

GROUNDED_KEYS = ("evidence_ids", "calculation_ids")


class AgentExecutionError(Exception):
    def __init__(self, agent_id: str, reason: str) -> None:
        super().__init__(f"{agent_id}: {reason}")
        self.agent_id = agent_id
        self.reason = reason


def ground(obj: Any, allowed: set[str]) -> tuple[Any, list[str]]:
    """Remove recursivamente IDs em evidence_ids/calculation_ids que o agente não recebeu."""
    rejected: list[str] = []

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                if k in GROUNDED_KEYS and isinstance(v, list):
                    kept = [i for i in v if isinstance(i, str) and i in allowed]
                    rejected.extend(i for i in v if i not in kept)
                    out[k] = kept
                else:
                    out[k] = walk(v)
            return out
        if isinstance(node, list):
            return [walk(i) for i in node]
        return node

    return walk(obj), rejected


def collect_ids(obj: Any) -> list[str]:
    ids: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k in GROUNDED_KEYS and isinstance(v, list):
                    ids.extend(i for i in v if isinstance(i, str))
                else:
                    walk(v)
        elif isinstance(node, list):
            for i in node:
                walk(i)

    walk(obj)
    return list(dict.fromkeys(ids))


class AgentRuntime:
    def __init__(self, provider: LLMProvider | None, model: str) -> None:
        self.provider = provider
        self.model = model

    async def run(
        self,
        agent: Agent,
        ctx: ExecutionContext,
        task: TaskSpec,
        toolbox: Toolbox,
        events: EventLog,
        evidence: EvidenceRegistry,
    ) -> AgentResult:
        agent_id = agent.card.agent_id
        events.emit(EventType.AGENT_STARTED, {"round": task.round}, agent_id=agent_id, task_id=task.task_id)

        # 1. gather — código; cada tool call autorizada/filtrada/auditada no Gateway
        tools_before = len(events.of_type(EventType.TOOL_CALLED))
        bundle = await agent.gather(ctx, task, toolbox)
        for oid in task.upstream_output_ids:
            rec = evidence.get(oid)
            if isinstance(rec, AgentOutputRecord):
                bundle.upstream_outputs.append(rec)
        tool_calls = len(events.of_type(EventType.TOOL_CALLED)) - tools_before

        # 2. reason — uma chamada, sem tools; 3. validate — grounding + regras do agente.
        # Se validate rejeitar, os problemas voltam ao modelo uma vez (mesma evidência, sem novas tools).
        prompt = agent.build_prompt(ctx, task, bundle)
        schema = OUTPUT_SCHEMAS[prompt.response_schema]
        messages = prompt.messages()
        usage = LLMUsage(model=self.model)
        rejected: list[str] = []
        validated: ValidatedOutput | None = None
        for attempt in range(2):
            raw, call_usage = await self._reason(agent_id, task, messages, schema, events)
            usage = _merge_usage(usage, call_usage)
            cleaned, rejected = ground(raw, bundle.allowed_ids())
            if rejected:
                events.emit(
                    EventType.GROUNDING_REJECTED,
                    {"rejected_ids": sorted(set(rejected))},
                    agent_id=agent_id,
                    task_id=task.task_id,
                )
            try:
                model_out = schema.model_validate(cleaned)
            except ValidationError as exc:
                raise AgentExecutionError(agent_id, f"output inválido após grounding: {exc.error_count()} erro(s)") from exc
            try:
                validated = agent.validate(ctx, task, model_out, bundle)
                break
            except OutputValidationError as exc:
                events.emit(
                    EventType.OUTPUT_REJECTED,
                    {"attempt": attempt + 1, "problems": exc.problems, "retry": attempt == 0},
                    agent_id=agent_id,
                    task_id=task.task_id,
                )
                if attempt == 1:
                    raise AgentExecutionError(
                        agent_id, f"output_validation_failed: {_short('; '.join(exc.problems), 300)}"
                    ) from exc
                messages = messages + [
                    Message(role="assistant", content=json.dumps(raw, ensure_ascii=False)),
                    Message(
                        role="user",
                        content="O backend rejeitou sua resposta na validação determinística:\n- "
                        + "\n- ".join(exc.problems)
                        + "\nCorrija usando SOMENTE as evidências, IDs e itens de catálogo fornecidos e devolva "
                        "SOMENTE o JSON completo, conforme o schema.",
                    ),
                ]
        assert validated is not None
        out_id = output_id(agent_id, task.round)
        evidence.register(AgentOutputRecord(id=out_id, agent_id=agent_id, round=task.round, output=validated.output))

        result = AgentResult(
            agent_id=agent_id,
            task_id=task.task_id,
            round=task.round,
            output=validated.output,
            output_id=out_id,
            evidence_ids=collect_ids(validated.output),
            calculation_ids=list(dict.fromkeys(validated.calculation_ids + [c.id for c in bundle.calculations])),
            assumptions=validated.assumptions,
            usage=usage,
            warnings=validated.warnings + ([f"grounding_rejected:{len(rejected)}"] if rejected else []),
            data_domains_accessed=sorted({s.resource_domain for s in bundle.sources}),
            tool_calls=tool_calls,
        )
        events.emit(
            EventType.AGENT_COMPLETED,
            {
                "round": task.round,
                "output_id": out_id,
                "warnings": result.warnings,
                "tool_calls": tool_calls,
                "data_domains_accessed": result.data_domains_accessed,
            },
            agent_id=agent_id,
            task_id=task.task_id,
        )
        return result

    # ------------------------------------------------------------------ reason

    async def _reason(
        self,
        agent_id: str,
        task: TaskSpec,
        messages: list[Message],
        schema: type[BaseModel],
        events: EventLog,
    ) -> tuple[dict[str, Any], LLMUsage]:
        if self.provider is None:
            raise AgentExecutionError(agent_id, "llm_unconfigured: defina LLM_API_KEY no .env")

        retries = 0
        usage = LLMUsage(model=self.model)
        for attempt in range(2):
            started = time.monotonic()
            try:
                resp = await self.provider.complete(model=self.model, messages=messages, response_schema=schema)
            except LLMError as exc:
                events.emit(
                    EventType.LLM_CALLED,
                    {"ok": False, "error": str(exc), "attempt": attempt + 1},
                    agent_id=agent_id,
                    task_id=task.task_id,
                )
                raise AgentExecutionError(agent_id, f"provider_error: {exc}") from exc
            prompt_chars = sum(len(m.content) for m in messages)
            usage = LLMUsage(
                model=resp.usage.model,
                tokens_in=usage.tokens_in + resp.usage.tokens_in,
                tokens_out=usage.tokens_out + resp.usage.tokens_out,
                tokens_cached=usage.tokens_cached + resp.usage.tokens_cached,
                usage_reported=(attempt == 0 or usage.usage_reported) and resp.usage.usage_reported,
                latency_ms=usage.latency_ms + (resp.usage.latency_ms or int((time.monotonic() - started) * 1000)),
                retries=retries,
                prompt_chars=usage.prompt_chars + prompt_chars,
            )
            events.emit(
                EventType.LLM_CALLED,
                {
                    "ok": True,
                    "attempt": attempt + 1,
                    "usage": resp.usage.model_dump() | {"prompt_chars": prompt_chars},
                },
                agent_id=agent_id,
                task_id=task.task_id,
            )
            try:
                obj = extract_json(resp.content or "")
                schema.model_validate(obj)  # só valida estrutura; grounding acontece no runtime
                return obj, usage
            except (ValueError, ValidationError) as exc:
                retries += 1
                messages = messages + [
                    Message(role="assistant", content=resp.content or ""),
                    Message(
                        role="user",
                        content=f"Sua resposta falhou na validação do schema: {_short(str(exc))}. "
                        "Devolva SOMENTE o JSON corrigido, conforme o schema.",
                    ),
                ]
        raise AgentExecutionError(agent_id, "schema_validation_failed_after_retry")


def _short(text: str, limit: int = 600) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def _merge_usage(total: LLMUsage, call: LLMUsage) -> LLMUsage:
    return LLMUsage(
        model=call.model or total.model,
        tokens_in=total.tokens_in + call.tokens_in,
        tokens_out=total.tokens_out + call.tokens_out,
        tokens_cached=total.tokens_cached + call.tokens_cached,
        usage_reported=(total.prompt_chars == 0 or total.usage_reported) and call.usage_reported,
        latency_ms=total.latency_ms + call.latency_ms,
        retries=total.retries + call.retries,
        prompt_chars=total.prompt_chars + call.prompt_chars,
    )
