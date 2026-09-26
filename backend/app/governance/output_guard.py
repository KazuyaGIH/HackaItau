"""Output Guard determinístico (ARCHITECTURE.md §14). Último filtro antes de HUMAN_REVIEW_REQUIRED.

Roda sobre o Report estruturado: redige secrets, referências a clientes fora do scope e valores de campos `never`;
move claims sem evidência para `uncertainties`; neutraliza linguagem de decisão; força decision_status.
Cada intervenção vira um finding GUARD_* em report.review.findings. Nunca é a única barreira.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.evidence import EvidenceRegistry
from app.core.schemas.context import CaseScope
from app.core.schemas.outputs import Finding
from app.core.schemas.report import Report, ReportItem
from app.data.repository import DataRepository
from app.governance.loader import load_resource_policies

REDACTED = "[REDACTED]"
NEUTRAL = "para avaliação humana"

SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(LLM_API_KEY|OPENAI_API_KEY|API_KEY|SECRET_KEY)\s*[=:]\s*\S+", re.IGNORECASE),
)
CLIENT_ID_RE = re.compile(r"\bCLIENTE-\d{3,}\b", re.IGNORECASE)
LANGUAGE_RE = re.compile(
    r"\b(cr[ée]dito (?:aprovad|negad|rejeitad)[ao]|opera[çc][ãa]o (?:aprovad|negad|rejeitad)a|"
    r"recomend(?:o|amos) (?:a )?aprova(?:r|[çc][ãa]o)|deve(?:mos)? (?:ser )?aprovad[ao]|aprova[çc][ãa]o autom[áa]tica|"
    r"alternativa preferida|melhor op[çc][ãa]o|sem (?:qualquer )?risco|retorno garantido|certamente|com certeza)\b",
    re.IGNORECASE,
)
NEGATION_RE = re.compile(r"\b(n[ãa]o|nunca|nem)\s+(\S+\s+){0,2}$", re.IGNORECASE)
_GROUNDED_SECTIONS = ("facts", "calculations", "favorable_factors", "risk_factors")
_MIN_FORBIDDEN_LEN = 4


@dataclass
class GuardResult:
    report: Report
    findings: list[Finding]
    redactions: dict[str, int] = field(default_factory=dict)

    @property
    def applied(self) -> bool:
        return bool(self.findings)


class OutputGuard:
    def __init__(self, repo: DataRepository, secret_values: list[str], scope: CaseScope) -> None:
        self._secrets = [s for s in secret_values if s]
        self._scope = scope
        self._forbidden_values = self._never_values(repo, scope)

    # ------------------------------------------------------------------ public

    def apply(self, report: Report, evidence: EvidenceRegistry, next_finding_seq: int) -> GuardResult:
        data = report.model_dump(mode="json")
        counts: dict[str, int] = {}

        def bump(k: str) -> None:
            counts[k] = counts.get(k, 0) + 1

        # 1–3, 5: redação/neutralização de texto em todo o relatório
        data = self._walk(data, bump)

        # 4: claims materiais sem evidência existente → uncertainties
        moved = 0
        known = evidence.ids()
        for section in _GROUNDED_SECTIONS:
            kept = []
            for item in data.get(section, []):
                ids = item.get("evidence_ids") or ([item["calculation_id"]] if "calculation_id" in item else [])
                if ids and all(i in known for i in ids):
                    kept.append(item)
                else:
                    moved += 1
                    if section != "calculations":
                        text = item.get("text", "")
                        data["uncertainties"].append(
                            ReportItem(
                                text=f"[sem evidência] {text}", evidence_ids=[], severity="info", code="GUARD_UNGROUNDED"
                            ).model_dump()
                        )
            data[section] = kept
        for alt in data.get("alternatives", []):
            if not alt.get("evidence_ids") or any(i not in known for i in alt["evidence_ids"]):
                moved += 1
                alt["evidence_ids"] = [i for i in alt.get("evidence_ids", []) if i in known]
        if moved:
            counts["GUARD_UNGROUNDED"] = moved

        # 6: estado final obrigatório
        if data.get("decision_status") != "ready_for_human_review":
            data["decision_status"] = "ready_for_human_review"
            bump("GUARD_STATUS")

        findings = []
        for i, (code, n) in enumerate(sorted(counts.items()), start=next_finding_seq):
            findings.append(
                Finding(
                    id=f"F-G-{i:03d}",
                    code=code,
                    severity="high" if code in ("GUARD_SECRET", "GUARD_SCOPE", "GUARD_FORBIDDEN_FIELD") else "low",
                    message=_MESSAGES[code].format(n=n),
                    owner_agent=None,
                    evidence_ids=[],
                    origin="output_guard",
                    status="informational",
                )
            )
        data["review"]["findings"] = data["review"]["findings"] + [f.model_dump(mode="json") for f in findings]
        return GuardResult(report=Report.model_validate(data), findings=findings, redactions=counts)

    # ------------------------------------------------------------------ text

    def _walk(self, node: Any, bump: Callable[[str], None]) -> Any:
        if isinstance(node, str):
            return self._clean(node, bump)
        if isinstance(node, dict):
            return {k: (v if k in _ID_KEYS else self._walk(v, bump)) for k, v in node.items()}
        if isinstance(node, list):
            return [self._walk(i, bump) for i in node]
        return node

    def _clean(self, text: str, bump: Callable[[str], None]) -> str:
        for s in self._secrets:
            if s in text:
                text = text.replace(s, REDACTED)
                bump("GUARD_SECRET")
        for pat in SECRET_PATTERNS:
            text, n = pat.subn(REDACTED, text)
            if n:
                bump("GUARD_SECRET")
        for m in list(CLIENT_ID_RE.finditer(text))[::-1]:
            if m.group(0).upper() not in self._scope.client_ids:
                text = text[: m.start()] + REDACTED + text[m.end() :]
                bump("GUARD_SCOPE")
        for value in self._forbidden_values:
            if value in text:
                text = text.replace(value, REDACTED)
                bump("GUARD_FORBIDDEN_FIELD")
        out, last = [], 0
        for m in LANGUAGE_RE.finditer(text):
            if NEGATION_RE.search(text[: m.start()]):
                continue
            out.append(text[last : m.start()] + NEUTRAL)
            last = m.end()
            bump("GUARD_LANGUAGE")
        return "".join(out) + text[last:] if out else text

    # ------------------------------------------------------------------ setup

    @staticmethod
    def _never_values(repo: DataRepository, scope: CaseScope) -> list[str]:
        policies = load_resource_policies()
        values: list[str] = []
        for cid in scope.client_ids:
            records = {
                "client_profile": [repo.get_client(cid)],
                "client_financials": [repo.get_financials(cid)],
                "agro_profile": [repo.get_agro_profile(cid)],
                "documents": repo.list_documents(cid, ["adversarial"]),
            }
            for domain, recs in records.items():
                never = policies[domain].never if domain in policies else []
                for rec in recs:
                    for f in never:
                        v = (rec or {}).get(f)
                        if isinstance(v, str) and len(v) >= _MIN_FORBIDDEN_LEN:
                            values.append(v)
        return values


_ID_KEYS = {
    "evidence_ids",
    "calculation_id",
    "calculation_ids",
    "thresholds_source_ids",
    "input_sources",
    "source_id",
    "id",
    "case_id",
    "client_id",
    "case_scope_client_ids",
    "sources",
}

_MESSAGES = {
    "GUARD_SECRET": "{n} trecho(s) com formato/valor de secret redigido(s).",
    "GUARD_SCOPE": "{n} referência(s) a cliente fora do CaseScope redigida(s).",
    "GUARD_FORBIDDEN_FIELD": "{n} valor(es) de campo `never` redigido(s).",
    "GUARD_UNGROUNDED": "{n} item(ns) sem evidência válida movido(s)/marcado(s).",
    "GUARD_LANGUAGE": "{n} expressão(ões) de decisão/certeza neutralizada(s).",
    "GUARD_STATUS": "decision_status forçado para ready_for_human_review.",
}
