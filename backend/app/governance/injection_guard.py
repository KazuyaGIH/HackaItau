"""Injection Guard (ARCHITECTURE.md §11.3): heurístico, roda no Gateway sobre cada registro. Marca; não bloqueia."""

import re
from typing import Any

from pydantic import BaseModel, Field

from app.core.schemas.context import CaseScope

CLIENT_REF_RE = re.compile(r"\bCLIENTE-\d{3,}\b", re.IGNORECASE)

INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE | re.DOTALL)
    for p in (
        r"ignore\w*\s+(as\s+|the\s+|all\s+|todas\s+as\s+)?(instru|previous|prior|anterior|regras|rules)",
        r"desconsidere\s+(as\s+)?(instru|regras)",
        r"system\s*prompt",
        r"voc[eê]\s+(agora\s+)?[eé]\s+(o\s+)?(admin|administrador|root|desenvolvedor)",
        r"you\s+are\s+now\s+(the\s+)?(admin|administrator|root|developer)",
        r"consulte\s+(os\s+dados\s+(financeiros\s+)?d[oe]\s+)?CLIENTE-\d+",
        r"\b(aprove|aprovar|approve)\s+(o\s+)?(cr[eé]dito|credit|imediatamente|now)",
        r"\b(revele|reveal|exiba|mostre)\s+(o\s+|a\s+|as\s+|os\s+)?(senha|secret|api[_\s-]?key|chave|token|prompt)",
        r"\b(execute|rode|run)\s+(o\s+)?(comando|command|sql|shell|script)",
    )
)


class ScanResult(BaseModel):
    flagged: bool = False
    matched_patterns: list[str] = Field(default_factory=list)
    out_of_scope_refs: list[str] = Field(default_factory=list)


def _texts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _texts(v)]
    if isinstance(value, list):
        return [t for v in value for t in _texts(v)]
    return []


def scan_record(record: dict[str, Any], scope: CaseScope) -> ScanResult:
    result = ScanResult()
    scope_ids = {c.upper() for c in scope.client_ids}
    for text in _texts({k: v for k, v in record.items() if k != "client_id"}):
        for pat in INJECTION_PATTERNS:
            if pat.search(text) and pat.pattern not in result.matched_patterns:
                result.matched_patterns.append(pat.pattern)
        for ref in CLIENT_REF_RE.findall(text):
            ref_u = ref.upper()
            if ref_u not in scope_ids and ref_u not in result.out_of_scope_refs:
                result.out_of_scope_refs.append(ref_u)
    result.flagged = bool(result.matched_patterns or result.out_of_scope_refs)
    return result
