"""Restrições automáticas não equivalem a qualidade semântica. Qualidade exige revisão cega."""

import json
import math
from collections import defaultdict

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

from app.agents.structuring.agent import _check_alternative
from app.core.schemas.events import EventType
from app.orchestration.plans import ELIGIBILITY, RISK, STRUCTURING

RUBRIC = {
    "grounding": "Afirmações sustentadas pelas fontes; sem inventar fatos ou garantias.",
    "risk": "Reconhece riscos materiais, contradições e incertezas; explica o bloqueio quando aplicável.",
    "structure": "Alternativas viáveis e condicionadas aos riscos; em bloqueios, pede o dado certo sem propor crédito.",
    "clarity": "Explicação útil ao analista, neutra, sem aprovação automática ou certeza indevida.",
}


class HumanReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_id: str
    reviewer: str = Field(min_length=1)
    grounding: StrictInt = Field(ge=0, le=3)
    risk: StrictInt = Field(ge=0, le=3)
    structure: StrictInt = Field(ge=0, le=3)
    clarity: StrictInt = Field(ge=0, le=3)
    critical_error: StrictBool
    rationale: str = Field(min_length=10)

    @field_validator("reviewer", "rationale")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("identificação e justificativa são obrigatórias")
        return value

    def accepted(self):
        return not self.critical_error and min(getattr(self, name) for name in RUBRIC) >= 2


def automatic_checks(rec, case):
    results = dict(rec.results)
    for result in rec.completed.values():
        results.setdefault(result.agent_id, result)
    checks = {"expected_status": rec.state.status.value == case["expected_status"]}
    if case["expected_status"] == "waiting_input":
        items = rec.state.missing_info.items if rec.state.missing_info else []
        checks["required_missing_items"] = set(case.get("missing", [])) <= set(items)
        checks["no_risk_calculation"] = not rec.evidence.calculations()
        checks["no_credit_proposal"] = rec.state.report is None
    else:
        checks["report_present"] = rec.state.report is not None
        metrics = next((c for c in rec.evidence.calculations() if c.name == "credit_metrics"), None)
        checks["expected_baseline"] = bool(metrics and metrics.inputs["productivity"] == case["expected_productivity"])
        risk = results.get(RISK)
        struct = results.get(STRUCTURING)
        catalog = {s.data["product_id"]: s.data for s in rec.evidence.sources() if s.resource_domain == "product_catalog"}
        alternatives = struct.output["alternatives"] if struct else []
        checks["valid_alternatives"] = len(alternatives) in (2, 3) and all(
            not _check_alternative(a, case["amount"], catalog, case["crop"]) for a in alternatives
        )
        risks = risk.output.get("main_risks", []) if risk else []
        addressed = {code.upper() for a in alternatives for code in a.get("addressed_risk_codes", [])}
        checks["material_risk_codes_addressed"] = bool(risk and struct) and all(
            r["code"].upper() in addressed for r in risks if r.get("severity") in ("high", "medium")
        )
        checks["risks_have_sources"] = bool(risks) and all(r.get("evidence_ids") for r in risks)
        checks["human_decision_preserved"] = rec.state.status.value == "human_review_required"
        findings = rec.state.report.review.findings if rec.state.report else []
        checks["no_open_validator_violation"] = not any(
            f.origin == "validator" and f.status == "open" and f.severity in ("medium", "high") for f in findings
        )
    # Estas intervenções são reportadas separadamente: são trabalho do backend, não acurácia do modelo.
    interventions = {
        "grounding_rejections": len(rec.events.of_type(EventType.GROUNDING_REJECTED)),
        "output_rejections": len(rec.events.of_type(EventType.OUTPUT_REJECTED)),
        "output_guard_interventions": len(rec.events.of_type(EventType.OUTPUT_GUARD_APPLIED)),
        "rework_rounds": rec.state.rework_rounds,
        "validation_warnings": sum(len(r.warnings) for r in rec.completed.values()),
    }
    eligible = results.get(ELIGIBILITY)
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "interventions": interventions,
        "eligibility": eligible.output if eligible else None,
    }


def wilson(passed, count):
    if not count:
        return None
    z, p = 1.96, passed / count
    denominator = 1 + z * z / count
    center = (p + z * z / (2 * count)) / denominator
    width = z * math.sqrt(p * (1 - p) / count + z * z / (4 * count * count)) / denominator
    return [round(max(0, center - width), 4), round(min(1, center + width), 4)]


def summarize(runs, reviews=None):
    reviews = reviews or {}
    groups = defaultdict(list)
    for run in runs:
        groups[run["architecture"], run["model_label"]].append(run)
    summary = []
    for (architecture, label), rows in sorted(groups.items()):
        reviewed = [r for r in rows if r["blind_id"] in reviews]
        accepted = sum(r["automatic"]["passed"] and reviews[r["blind_id"]].accepted() for r in reviewed)
        complete = len(reviewed) == len(rows)
        cost_known = all(r["cost_usd"] is not None for r in rows)
        cost = sum(r["cost_usd"] for r in rows) if cost_known else None
        summary.append(
            {
                "architecture": architecture,
                "model_label": label,
                "model": rows[0]["model"],
                "reasoning_effort": rows[0].get("reasoning_effort"),
                "runs": len(rows),
                "automatic_passes": sum(r["automatic"]["passed"] for r in rows),
                "errors": sum(r["status"] == "failed" for r in rows),
                "reviewed": len(reviewed),
                "accepted": accepted if complete else None,
                "accepted_rate": accepted / len(rows) if complete else None,
                "accepted_rate_ci95": wilson(accepted, len(rows)) if complete else None,
                "calls": sum(r["calls"] for r in rows),
                "tokens_in": sum(r["tokens_in"] for r in rows),
                "tokens_out": sum(r["tokens_out"] for r in rows),
                "usage_complete": all(r["usage_complete"] for r in rows),
                "total_cost_usd": cost,
                "cost_per_accepted_usd": cost / accepted if complete and accepted and cost_known else None,
                "mean_latency_seconds": sum(r["latency_seconds"] for r in rows) / len(rows),
            }
        )
    return summary


def load_reviews(path, valid_ids):
    items = json.loads(path.read_text(encoding="utf-8"))
    reviews = {}
    for item in items:
        review = HumanReview.model_validate(item)
        if review.blind_id not in valid_ids or review.blind_id in reviews:
            raise ValueError("ID de revisão desconhecido ou duplicado")
        reviews[review.blind_id] = review
    return reviews
