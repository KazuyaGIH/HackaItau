"""Desempenho dos agentes, calculado a partir do Event Log e dos resultados dos cases em memória.

Definições (também exibidas na UI):
- conclusão: tentativa encerrada com AGENT_COMPLETED, inclusive após correção; não mede qualidade factual;
- validação sem correções: execução concluída sem rejeição de saída/referências ou nova resposta do modelo;
- correção e devolução são marcas da mesma tentativa e não são subtraídas duas vezes;
- devolvida pela revisão: o Revisor reabriu a tarefa (retrabalho) com o agente como responsável;
- falha: a execução parou com erro (ex.: provedor do modelo indisponível).
- contexto: caracteres dos prompts realmente enviados (~4 caracteres por token) contra um agente generalista
  estimado, que receberia todas as evidências do case e os playbooks de todos os agentes em cada rodada de análise.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.agents.registry import AgentRegistry
from app.core.schemas.events import EventType
from app.core.schemas.evidence import EvidenceBundle
from app.core.schemas.outputs import OUTPUT_SCHEMAS
from app.core.store import CaseStore
from app.llm.prompting import UNTRUSTED_RULES, render_evidence, render_schema
from app.orchestration.plans import REVIEW

CHARS_PER_TOKEN = 4


@dataclass
class Attempt:
    agent_id: str
    task_id: str | None
    completed: bool = False
    failed: bool = False
    corrected: bool = False
    reopened: bool = False
    calls: int = 0


def _tokens(chars: int) -> int:
    return round(chars / CHARS_PER_TOKEN)


def compute_metrics(store: CaseStore, registry: AgentRegistry) -> dict[str, Any]:
    agents: dict[str, dict[str, Any]] = {
        a: defaultdict(int) | {"latencies": []}
        for a in registry.ids()  # type: ignore[operator]
    }
    generalist_static = _generalist_static_chars(registry)

    cases = reports = decisions = 0
    squad_chars = generalist_chars = squad_calls = generalist_calls = 0
    tokens_in = tokens_out = 0

    for rec in store.all():
        cases += 1
        reports += rec.state.report is not None
        events = rec.events.list_after(0)
        attempts: list[Attempt] = []
        active: dict[str, Attempt] = {}
        latest_completed: dict[str, Attempt] = {}
        case_prompt_chars = case_calls = rounds = 0
        # achados materiais por rodada de revisão: (code, owner) — confirmados quando somem depois do retrabalho
        material_by_round: dict[int, set[tuple[str, str]]] = defaultdict(set)
        rework_rounds: list[int] = []
        for e in events:
            a = e.agent_id
            p = e.payload
            m = agents.get(a or "")
            if e.type in (EventType.HUMAN_APPROVED, EventType.HUMAN_ADJUSTMENT_REQUESTED):
                decisions += 1
            if e.type == EventType.REVIEW_STARTED:
                rounds += 1
            if m is None:
                continue
            attempt = active.get(a)
            if e.type == EventType.AGENT_STARTED:
                m["runs"] += 1
                attempt = Attempt(str(a), e.task_id)
                attempts.append(attempt)
                active[str(a)] = attempt
            elif e.type == EventType.AGENT_COMPLETED:
                m["completed"] += 1
                m["tool_calls"] += int(p.get("tool_calls", 0))
                if attempt is not None:
                    attempt.completed = True
                    latest_completed[str(a)] = attempt
            elif e.type in (EventType.OUTPUT_REJECTED, EventType.GROUNDING_REJECTED) and e.task_id:
                if attempt is not None and attempt.task_id == e.task_id:
                    attempt.corrected = True
            elif e.type == EventType.EXECUTION_FAILED:
                m["failed"] += 1
                if attempt is not None and not attempt.completed:
                    attempt.failed = True
            elif e.type == EventType.PERMISSION_DENIED:
                m["denied"] += 1
            elif e.type == EventType.TASK_REOPENED and a == p.get("action"):
                m["adjusted_by_human" if p.get("source") == "human" else "reopened_by_review"] += 1
                if p.get("source") != "human" and a in latest_completed:
                    latest_completed[a].reopened = True
            elif e.type == EventType.REVIEW_ISSUE_FOUND:
                m["findings_raised"] += 1
                if p.get("severity") == "high":
                    m["material_findings"] += 1
                    material_by_round[rounds].add((str(p.get("code")), str(p.get("owner"))))
            elif e.type == EventType.REVIEW_COMPLETED and p.get("reexecution_required"):
                m["reworks_triggered"] += 1
                rework_rounds.append(rounds)
            elif e.type == EventType.LLM_CALLED and p.get("ok"):
                if attempt is not None and attempt.task_id == e.task_id:
                    attempt.calls += 1
                    # Correções de schema também podem ocorrer sem um evento OUTPUT_REJECTED.
                    attempt.corrected |= attempt.calls > 1
                usage = p.get("usage") or {}
                m["llm_calls"] += 1
                m["tokens_in"] += int(usage.get("tokens_in", 0))
                m["tokens_out"] += int(usage.get("tokens_out", 0))
                m["prompt_chars"] += int(usage.get("prompt_chars", 0))
                tokens_in += int(usage.get("tokens_in", 0))
                tokens_out += int(usage.get("tokens_out", 0))
                case_prompt_chars += int(usage.get("prompt_chars", 0))
                case_calls += 1
        for attempt in attempts:
            m = agents[attempt.agent_id]
            if attempt.completed:
                m["validator_fixes"] += int(attempt.corrected)
                m["validation_clean"] += int(not attempt.corrected)
                m["hits"] += int(not attempt.corrected and not attempt.reopened)
            if not attempt.completed and not attempt.failed:
                m["in_progress"] += 1
        for result in rec.completed.values():
            if result.agent_id in agents and result.usage.latency_ms:
                agents[result.agent_id]["latencies"].append(result.usage.latency_ms)
        for r in rework_rounds:
            if r + 1 <= rounds:  # houve revisão depois do retrabalho
                agents[REVIEW]["confirmed_by_rework"] += len(material_by_round[r] - material_by_round[r + 1])
        if rec.state.review is not None:
            for f in rec.state.review.findings:
                owner = agents.get(f.owner_agent or "")
                if owner is not None and f.severity in ("high", "medium"):
                    owner["findings_owned"] += 1

        if case_calls and case_prompt_chars:
            # generalista: um prompt com TODAS as evidências do case, renderizadas como os agentes as recebem
            everything = EvidenceBundle(sources=rec.evidence.sources(), calculations=rec.evidence.calculations())
            case_rounds = max(1, rounds)
            squad_chars += case_prompt_chars
            squad_calls += case_calls
            generalist_chars += case_rounds * (len(render_evidence(everything)) + generalist_static)
            generalist_calls += case_rounds

    return {
        "cases": cases,
        "reports": reports,
        "human_decisions": decisions,
        "tokens": {"input": tokens_in, "output": tokens_out},
        "context": _context(squad_chars, squad_calls, generalist_chars, generalist_calls),
        "agents": [_agent_view(a, agents[a], registry) for a in registry.ids()],
    }


def _generalist_static_chars(registry: AgentRegistry) -> int:
    """O que um agente único precisaria carregar em todo prompt: papéis e playbooks de todos os especialistas,
    os schemas de saída de todos eles e as regras de dados não confiáveis (uma vez)."""
    total = len(UNTRUSTED_RULES)
    for agent_id in registry.ids():
        card = registry.card(agent_id)
        total += len(card.name) + len(card.description) + len(", ".join(card.forbidden_actions))
        total += len(registry.get(agent_id).playbook) + len(render_schema(OUTPUT_SCHEMAS[card.output_schema]))
    return total


def _context(squad_chars: int, squad_calls: int, generalist_chars: int, generalist_calls: int) -> dict[str, Any]:
    squad = _tokens(squad_chars)
    generalist = _tokens(generalist_chars)
    per_call_squad = _tokens(squad_chars // squad_calls) if squad_calls else 0
    per_call_generalist = _tokens(generalist_chars // generalist_calls) if generalist_calls else 0
    return {
        "squad_tokens": squad,
        "squad_calls": squad_calls,
        "generalist_tokens": generalist,
        "generalist_calls": generalist_calls,
        "saved_tokens": generalist - squad,
        "saved_pct": round(100 * (generalist - squad) / generalist, 1) if generalist else None,
        "per_call_squad": per_call_squad,
        "per_call_generalist": per_call_generalist,
        "per_call_saved_pct": (
            round(100 * (per_call_generalist - per_call_squad) / per_call_generalist, 1) if per_call_generalist else None
        ),
    }


def _agent_view(agent_id: str, m: dict[str, Any], registry: AgentRegistry) -> dict[str, Any]:
    card = registry.card(agent_id)
    completed, failed = m["completed"], m["failed"]
    reviewed = agent_id == REVIEW
    errors = m["reopened_by_review"] + failed
    hits = m["hits"]
    latencies = m["latencies"]
    return {
        "agent_id": agent_id,
        "name": card.name,
        "version": card.version,
        "description": card.description,
        "capabilities": card.capabilities,
        "tools": card.tools,
        "data_domains": card.allowed_data_domains,
        "forbidden_actions": card.forbidden_actions,
        "runs": m["runs"],
        "completed": completed,
        "failed": failed,
        "in_progress": m["in_progress"],
        "completion_pct": round(100 * completed / (completed + failed), 1) if completed + failed else None,
        "validation_clean": m["validation_clean"],
        "validation_first_pass_pct": round(100 * m["validation_clean"] / completed, 1) if completed else None,
        "hits": hits,
        "validator_fixes": m["validator_fixes"],
        "reopened_by_review": m["reopened_by_review"],
        "adjusted_by_human": m["adjusted_by_human"],
        "errors": errors,
        # Alias legado: mede ausência de intervenções, nunca acurácia factual.
        "accuracy_pct": round(100 * hits / (completed + failed), 1) if completed + failed else None,
        "findings_owned": m["findings_owned"],
        "tool_calls": m["tool_calls"],
        "denied_calls": m["denied"],
        "llm_calls": m["llm_calls"],
        "tokens_in": m["tokens_in"],
        "tokens_out": m["tokens_out"],
        "avg_context_tokens": _tokens(m["prompt_chars"] // m["llm_calls"]) if m["llm_calls"] else 0,
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
        # só o Revisor: o que ele encontrou e quanto disso o retrabalho confirmou
        "reviewer": (
            {
                "findings_raised": m["findings_raised"],
                "material_findings": m["material_findings"],
                "reworks_triggered": m["reworks_triggered"],
                "confirmed_by_rework": m["confirmed_by_rework"],
                "confirmation_pct": (
                    round(100 * m["confirmed_by_rework"] / m["material_findings"], 1) if m["material_findings"] else None
                ),
            }
            if reviewed
            else None
        ),
    }
